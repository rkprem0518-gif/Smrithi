"""A fresh Smriti: no sample people, a guided setup, removing one profile, and starting over.

Calls are simulated (DEMO_MODE=1): Bolna is never contacted.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from app.db import get_engine
from app.settings import get_settings
from tests.test_api import PHONE, _make_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("SEED_FAMILY_DEMO", raising=False)
    app = _make_app(tmp_path, monkeypatch)
    monkeypatch.delenv("SEED_FAMILY_DEMO", raising=False)  # the default: start empty
    get_settings.cache_clear()
    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()
    get_engine.cache_clear()


def me(c, app: str = "") -> dict:
    return c.get(f"{app}/api/auth/me").json()


def family_setup(c, name: str = "Arjun Mehta") -> dict:
    """What the welcome screens do: sign up, add a parent, pick call times."""
    r = c.post("/api/auth/signup", json={"name": name, "relation": "son"})
    assert r.status_code == 201, r.text
    parent = c.post("/api/people/parents", json={"full_name": "Kamala Rao", "call_name": "Amma", "age": 71,
                                                  "city": "Mysuru", "language": "kn", "relation": "son"})
    assert parent.status_code == 201, parent.text
    sched = c.post("/api/family/schedules", json={"label": "Weekly chat", "days": [6], "time": "10:30",
                                                   "questions": ["Did you take your BP tablet?"],
                                                   "parent_id": parent.json()["id"]})
    assert sched.status_code == 201, sched.text
    return parent.json()


def test_a_fresh_server_has_no_people(client) -> None:
    for app in ("", "/elder", "/care"):
        out = me(client, app)
        assert out["user"] is None and out["demo_users"] == []


def test_a_new_family_sets_up_and_makes_a_first_call(client) -> None:
    amma = family_setup(client)
    out = me(client)
    assert out["user"]["name"] == "Arjun Mehta" and out["user"]["role"] == "family"
    assert [p["call_name"] for p in out["parents"]] == ["Amma"]
    assert [u["name"] for u in me(client, "/elder")["demo_users"]] == ["Kamala Rao"]  # Amma can now log in

    r = client.post("/api/family/call", json={"phone": PHONE, "parent_id": amma["id"]})
    assert r.status_code == 201, r.text
    for _ in range(200):  # the simulated call plays out in the background
        timeline = client.get(f"/api/family/timeline?parent_id={amma['id']}").json()
        if any(i.get("status") == "done" for i in timeline.get("items", [])):
            break
        time.sleep(0.05)
    else:
        pytest.fail("the simulated call never finished")


def test_the_care_team_signs_up_and_sees_every_family(client) -> None:
    family_setup(client)
    r = client.post("/care/api/auth/signup", json={"name": "Dr. Asha Rao", "org": "Mysuru Memory Clinic"})
    assert r.status_code == 201, r.text
    patients = client.get("/care/api/care/patients").json()["items"]
    assert [p["call_name"] for p in patients] == ["Amma"]
    assert client.get("/care/api/care/queue").status_code == 200


def test_elders_cannot_sign_up_themselves_and_names_are_required(client) -> None:
    assert client.post("/elder/api/auth/signup", json={"name": "Kamala"}).status_code == 400
    assert client.post("/api/auth/signup", json={"name": "P"}).status_code == 422


def test_only_the_family_in_the_circle_removes_a_profile(client) -> None:
    amma = family_setup(client)
    elder_id = me(client, "/elder")["demo_users"][0]["id"]
    assert client.post("/elder/api/auth/demo-login", json={"user_id": elder_id}).status_code == 200
    assert client.delete(f"/elder/api/people/parents/{amma['id']}").status_code == 403  # not the elder's job
    stranger = TestClient(client.app)
    stranger.post("/api/auth/signup", json={"name": "Someone Else"})
    assert stranger.delete(f"/api/people/parents/{amma['id']}").status_code == 404  # not in that circle

    assert client.delete(f"/api/people/parents/{amma['id']}").json() == {"removed": "Amma"}
    assert me(client)["parents"] == []
    assert me(client, "/elder")["demo_users"] == []  # Amma's elder login went with the profile
    assert client.get("/elder/api/auth/me").json()["user"] is None


def test_start_over_deletes_everyone(client) -> None:
    family_setup(client)
    client.post("/care/api/auth/signup", json={"name": "Dr. Asha Rao"})
    assert client.post("/api/people/start-over").json()["removed"] == 1
    for app in ("", "/elder", "/care"):
        out = me(client, app)
        assert out["user"] is None and out["demo_users"] == []


def test_sample_family_on_request(client) -> None:
    assert client.post("/api/auth/sample-family").status_code == 201
    assert {u["name"] for u in me(client)["demo_users"]} >= {"Ravi Rao"}
    assert client.post("/api/auth/sample-family").status_code == 201  # twice is harmless
    assert len(me(client, "/elder")["demo_users"]) == 1
