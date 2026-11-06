"""Connect a Bolna account from the app (API key pasted in the family app), and one address for all three apps.

Bolna is always faked here (respx): no real key, no real call, no credits.
"""

from __future__ import annotations

import json
from itertools import count

import pytest
import respx
from fastapi.testclient import TestClient

from app.db import get_engine
from app.settings import get_settings
from tests.test_api import BASE, PHONE, _make_app

KEY = "bn-test-key-abcd1234"


def login(client, user_id: str, prefix: str = "") -> None:
    assert client.post(f"{prefix}/api/auth/demo-login", json={"user_id": user_id}).status_code == 200


@pytest.fixture
def client(tmp_path, monkeypatch):
    app = _make_app(tmp_path, monkeypatch, SEED_FAMILY_DEMO="1")
    with respx.mock(base_url=BASE, assert_all_called=False) as mock, TestClient(app) as c:
        c.bolna = mock  # type: ignore[attr-defined]
        yield c
    get_settings.cache_clear()
    get_engine.cache_clear()


def _fake_bolna(client, wallet: float = 500) -> respx.Route:
    ids = count(1)
    client.bolna.get("/user/me").respond(200, json={"wallet": wallet})
    return client.bolna.post("/v2/agent").mock(
        side_effect=lambda request: respx.MockResponse(200, json={"agent_id": f"made-{next(ids)}"})
    )


def test_family_connects_bolna_and_calls_become_real(client) -> None:
    agents = _fake_bolna(client)
    call = client.bolna.post("/call").respond(200, json={"execution_id": "ex-1", "status": "queued"})
    login(client, "u-ravi")
    mode = client.get("/api/auth/call-mode").json()
    assert mode["available"] is False and mode["bolna"]["can_connect"] is True and mode["can_manage"] is True

    r = client.post("/api/auth/bolna", json={"api_key": KEY})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["connected"] is True and out["source"] == "app" and out["created"] == ["checkin", "family", "memory"]
    assert out["key_hint"] == "…1234" and KEY not in r.text  # the key never goes back to a browser
    assert agents.call_count == 3
    names = {json.loads(c.request.content)["agent_config"]["agent_name"] for c in agents.calls}
    assert len(names) == 3
    assert not call.called  # connecting places no call

    mode = client.get("/api/auth/call-mode").json()
    assert mode["available"] is True and mode["live"] is False and mode["wallet"] == 500
    assert KEY not in json.dumps(mode)

    r = client.post("/api/family/call", json={"phone": PHONE})
    assert r.status_code == 201 and not call.called  # still simulated until the switch is on
    assert client.put("/api/auth/call-mode", json={"live": True}).json()["live"] is True
    r = client.post("/api/family/call", json={"phone": PHONE})
    assert r.status_code == 201, r.text
    assert call.called
    sent = call.calls.last.request
    assert sent.headers["Authorization"] == f"Bearer {KEY}"
    assert json.loads(sent.content)["agent_id"] == "made-1"  # the check-in agent made on connect

    r = client.delete("/api/auth/bolna")
    assert r.status_code == 200 and r.json()["source"] == "none"
    mode = client.get("/api/auth/call-mode").json()
    assert mode["available"] is False and mode["live"] is False


def test_existing_agents_are_reused(client) -> None:
    agents = _fake_bolna(client)
    login(client, "u-ravi")
    r = client.post("/api/auth/bolna", json={"api_key": KEY, "checkin_agent_id": "mine-1", "family_agent_id": "mine-2"})
    assert r.status_code == 200, r.text
    assert r.json()["created"] == ["memory"] and agents.call_count == 1


def test_wrong_key_is_rejected_and_nothing_is_stored(client) -> None:
    client.bolna.get("/user/me").respond(401, json={"message": "invalid key"})
    login(client, "u-ravi")
    r = client.post("/api/auth/bolna", json={"api_key": KEY})
    assert r.status_code == 400 and "didn't accept" in r.json()["detail"]
    assert client.get("/api/auth/bolna").json()["source"] == "none"
    assert client.post("/api/auth/bolna", json={"api_key": "short"}).status_code == 400


def test_only_family_or_care_team_can_connect(client) -> None:
    _fake_bolna(client)
    login(client, "u-appa")
    assert client.post("/api/auth/bolna", json={"api_key": KEY}).status_code == 403
    assert client.get("/api/auth/call-mode").json()["can_manage"] is False
    client.cookies.clear()
    login(client, "u-meera")
    assert client.post("/api/auth/bolna", json={"api_key": KEY}).status_code == 200


def test_offline_only_server_never_takes_a_key(tmp_path, monkeypatch) -> None:
    app = _make_app(tmp_path, monkeypatch, SEED_FAMILY_DEMO="1", ALLOW_APP_KEYS="0")
    with respx.mock(base_url=BASE, assert_all_called=False) as mock, TestClient(app) as c:
        me = mock.get("/user/me").respond(200, json={"wallet": 1})
        login(c, "u-ravi")
        assert c.get("/api/auth/call-mode").json()["bolna"]["can_connect"] is False
        assert c.post("/api/auth/bolna", json={"api_key": KEY}).status_code == 409
        assert not me.called
    get_settings.cache_clear()
    get_engine.cache_clear()


def test_a_key_added_in_the_app_takes_priority_over_env(tmp_path, monkeypatch) -> None:
    app = _make_app(tmp_path, monkeypatch, SEED_FAMILY_DEMO="1", DEMO_MODE="0", BOLNA_API_KEY="env-key-99999",
                    BOLNA_AGENT_ID="ag-1", BOLNA_AGENT_ID_CHECKIN="ag-c")
    with respx.mock(base_url=BASE, assert_all_called=False) as mock, TestClient(app) as c:
        mock.get("/user/me").respond(200, json={"wallet": 10})
        mock.post("/v2/agent").respond(200, json={"agent_id": "app-agent"})
        call = mock.post("/call").respond(200, json={"execution_id": "ex-9", "status": "queued"})
        login(c, "u-ravi")
        status = c.get("/api/auth/bolna").json()
        assert status["source"] == "env" and status["can_connect"] is True and "env-key" not in json.dumps(status)
        assert c.delete("/api/auth/bolna").status_code == 409  # nothing added in the app to disconnect

        assert c.post("/api/auth/bolna", json={"api_key": KEY}).json()["source"] == "app"
        c.put("/api/auth/call-mode", json={"live": True})
        assert c.post("/api/family/call", json={"phone": PHONE}).status_code == 201
        assert call.calls.last.request.headers["Authorization"] == f"Bearer {KEY}"  # the app key is used

        assert c.delete("/api/auth/bolna").json()["source"] == "env"  # back to the .env key
        c.put("/api/auth/call-mode", json={"live": True})
        assert c.post("/api/family/call", json={"phone": PHONE}).status_code == 201
        assert call.calls.last.request.headers["Authorization"] == "Bearer env-key-99999"
    get_settings.cache_clear()
    get_engine.cache_clear()


def test_three_apps_on_one_address(client) -> None:
    assert client.get("/elder", follow_redirects=False).headers["location"] == "/elder/smriti.html"
    assert client.get("/care/", follow_redirects=False).headers["location"] == "/care/smriti.html"
    page = client.get("/elder/smriti.html")
    assert page.status_code == 200 and "smriti-apps.js" in page.text
    assert client.get("/care/smriti.js").status_code == 200
    assert client.get("/elder/api/auth/me").json()["app"] == "elder"
    assert client.get("/care/api/auth/me").json()["app"] == "clinic"
    me = client.get("/api/auth/me").json()
    assert me["app"] == "family"

    login(client, "u-appa", "/elder")  # each app keeps its own login, even on one address
    assert client.get("/elder/api/auth/me").json()["user"]["id"] == "u-appa"
    assert client.get("/api/auth/me").json()["user"] is None
    login(client, "u-meera", "/care")
    assert client.get("/care/api/auth/me").json()["user"]["id"] == "u-meera"
    assert client.get("/elder/api/auth/me").json()["user"]["id"] == "u-appa"
    links = client.get("/elder/api/auth/me").json()["ports"]
    assert links == {"family": "/smriti.html", "elder": "/elder/smriti.html", "clinic": "/care/smriti.html"}
    assert client.get("/elder/api/care/patients").status_code == 403  # the elder is not the care team


def test_hosted_server_uses_one_address_from_the_root(tmp_path, monkeypatch) -> None:
    app = _make_app(tmp_path, monkeypatch, SEED_FAMILY_DEMO="1", ONE_ADDRESS="1", FAMILY_PORT="10000",
                    ELDER_PORT="8001")
    with TestClient(app, base_url="http://testserver:8001") as c:  # port numbers mean nothing on one address
        assert c.get("/", follow_redirects=False).headers["location"] == "/smriti.html"
        me = c.get("/api/auth/me").json()
        assert me["app"] == "family" and me["ports"]["elder"] == "/elder/smriti.html"
    get_settings.cache_clear()
    get_engine.cache_clear()


def test_poller_and_webhook_use_the_key_added_in_the_app(client) -> None:
    import asyncio

    from app.family import bolna_link
    from app.services.bolna_client import BolnaClient
    from app.services.poller import poll_once

    _fake_bolna(client)
    client.bolna.post("/call").respond(200, json={"execution_id": "ex-7", "status": "queued"})
    login(client, "u-ravi")
    assert bolna_link.current(get_settings()).demo_mode is True  # nothing connected yet: the poller stays idle
    client.post("/api/auth/bolna", json={"api_key": KEY})
    client.put("/api/auth/call-mode", json={"live": True})
    assert client.post("/api/family/call", json={"phone": PHONE}).status_code == 201
    execution = client.bolna.get("/executions/ex-7").respond(200, json={"id": "ex-7", "status": "in-progress"})
    current = bolna_link.current(get_settings())
    assert current.demo_mode is False and current.bolna_api_key == KEY

    async def sweep() -> int:
        async with BolnaClient.from_settings(current) as c:
            return await poll_once(current, c)

    assert asyncio.run(sweep()) == 1
    assert execution.calls.last.request.headers["Authorization"] == f"Bearer {KEY}"
