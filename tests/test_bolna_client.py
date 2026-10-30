import json
import sys
from pathlib import Path

import httpx
import pytest
import respx

from app.config_loader import agent_prompt, agent_template, scoring_config
from app.services.agent_builder import build_agent_payload
from app.services.bolna_client import (
    BolnaAuthError,
    BolnaClient,
    BolnaClientError,
    BolnaNetworkError,
    BolnaNotFound,
    BolnaRateLimited,
    BolnaServerError,
)
from app.settings import Settings

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import check_live  # noqa: E402

BASE = "https://api.bolna.ai"


def client() -> BolnaClient:
    return BolnaClient(api_key="test-key", base_url=BASE, backoff=0)


@respx.mock
async def test_create_agent_sends_payload_and_returns_id() -> None:
    route = respx.post(f"{BASE}/v2/agent").respond(201, json={"agent_id": "ag-1", "state": "created"})
    async with client() as c:
        assert await c.create_agent({"agent_config": {}, "agent_prompts": {}}) == "ag-1"
    req = route.calls.last.request
    assert req.headers["Authorization"] == "Bearer test-key"
    assert json.loads(req.content) == {"agent_config": {}, "agent_prompts": {}}


@respx.mock
async def test_update_agent_uses_put() -> None:
    route = respx.put(f"{BASE}/v2/agent/ag-1").respond(200, json={"agent_id": "ag-1", "status": "updated"})
    async with client() as c:
        await c.update_agent("ag-1", {"agent_config": {}, "agent_prompts": {}})
    assert route.called


@respx.mock
async def test_make_call_payload() -> None:
    route = respx.post(f"{BASE}/call").respond(200, json={"message": "done", "status": "queued", "execution_id": "ex-1"})
    async with client() as c:
        ex = await c.make_call("ag-1", "+919876543210", {"session_id": "s1"}, "+918000000000")
    assert ex == "ex-1"
    assert json.loads(route.calls.last.request.content) == {
        "agent_id": "ag-1", "recipient_phone_number": "+919876543210",
        "from_phone_number": "+918000000000", "user_data": {"session_id": "s1"},
    }


@respx.mock
async def test_make_call_omits_empty_from_number() -> None:
    route = respx.post(f"{BASE}/call").respond(200, json={"execution_id": "ex-1"})
    async with client() as c:
        await c.make_call("ag-1", "+919876543210")
    assert "from_phone_number" not in json.loads(route.calls.last.request.content)


@respx.mock
async def test_retries_5xx_then_succeeds() -> None:
    route = respx.get(f"{BASE}/executions/ex-1").mock(side_effect=[
        httpx.Response(502), httpx.Response(503), httpx.Response(200, json={"status": "completed"}),
    ])
    async with client() as c:
        assert (await c.get_execution("ex-1"))["status"] == "completed"
    assert route.call_count == 3


@respx.mock
async def test_gives_up_after_three_retries() -> None:
    route = respx.get(f"{BASE}/executions/ex-1").respond(500, json={"message": "boom"})
    async with client() as c:
        with pytest.raises(BolnaServerError):
            await c.get_execution("ex-1")
    assert route.call_count == 4  # 1 try + 3 retries


@respx.mock
async def test_network_errors_are_retried_then_typed() -> None:
    route = respx.get(f"{BASE}/user/me").mock(side_effect=httpx.ConnectError("down"))
    async with client() as c:
        with pytest.raises(BolnaNetworkError):
            await c.get_user_me()
    assert route.call_count == 4


@pytest.mark.parametrize(
    ("status", "exc"),
    [(400, BolnaClientError), (401, BolnaAuthError), (403, BolnaAuthError), (404, BolnaNotFound), (422, BolnaClientError)],
)
@respx.mock
async def test_4xx_is_not_retried(status, exc) -> None:
    route = respx.post(f"{BASE}/call").respond(status, json={"error": status, "message": "nope"})
    async with client() as c:
        with pytest.raises(exc) as info:
            await c.make_call("ag-1", "+919876543210")
    assert route.call_count == 1
    assert info.value.status_code == status


@respx.mock
async def test_429_carries_retry_after() -> None:
    respx.post(f"{BASE}/call").respond(429, json={"message": "warming up", "retry_after_seconds": 95})
    async with client() as c:
        with pytest.raises(BolnaRateLimited) as info:
            await c.make_call("ag-1", "+919876543210")
    assert info.value.retry_after == 95


def test_missing_key_is_an_auth_error() -> None:
    with pytest.raises(BolnaAuthError):
        BolnaClient(api_key="")


@respx.mock
async def test_web_call_session() -> None:
    route = respx.post(f"{BASE}/web-call/session").respond(200, json={"run_id": "run-1", "expires_in": 120})
    async with client() as c:
        assert (await c.create_web_call_session("ag-1", {"session_id": "s1"}))["run_id"] == "run-1"
    assert json.loads(route.calls.last.request.content)["agent_id"] == "ag-1"


# ---------------------------------------------------------------- agent payload

def test_agent_payload_shape() -> None:
    s = Settings(_env_file=None, max_call_minutes=8)
    payload = build_agent_payload(s, agent_template(), agent_prompt(), scoring_config())
    cfg = payload["agent_config"]
    assert set(payload) == {"agent_config", "agent_prompts"}
    assert "smriti_markers" not in json.dumps(payload)
    assert cfg["tasks"][0]["task_config"]["call_terminate"] == 480
    assert "webhook_url" not in cfg  # localhost is not reachable by Bolna; the poller is used
    assert "{{word_list}}" in payload["agent_prompts"]["task_1"]["system_prompt"]
    tools = cfg["tasks"][0]["tools_config"]
    assert set(tools) >= {"llm_agent", "synthesizer", "transcriber", "input", "output"}
    assert "keywords" not in tools["transcriber"]


def test_agent_payload_sets_public_webhook() -> None:
    s = Settings(_env_file=None, public_base_url="https://smriti.example.org", bolna_webhook_token="tok")
    payload = build_agent_payload(s, agent_template(), agent_prompt())
    assert payload["agent_config"]["webhook_url"] == "https://smriti.example.org/api/bolna/webhook?token=tok"


def test_prompt_never_says_dementia_except_in_the_ban() -> None:
    prompt = agent_prompt().lower()
    assert prompt.count("dementia") == 1  # only inside the "NEVER say" rule


def test_markers_in_prompt_match_config() -> None:
    prompt = agent_prompt()
    for name, phrases in agent_template()["smriti_markers"].items():
        assert phrases[0] in prompt, name


# ---------------------------------------------------------------- check_live

def live_settings(**kw) -> Settings:
    return Settings(_env_file=None, bolna_api_key="k", bolna_agent_id="ag-1", bolna_retry_backoff_seconds=0, **kw)


@respx.mock
async def test_check_live_ready() -> None:
    respx.get(f"{BASE}/user/me").respond(200, json={"name": "Asha", "wallet": 42.5, "concurrency": {"max": 10, "current": 0}})
    respx.get(f"{BASE}/v2/agent/ag-1").respond(200, json={"id": "ag-1", "agent_name": "Smriti", "agent_status": "processed"})
    ready, lines = await check_live.check(live_settings())
    assert ready, lines
    assert any("42.5" in line for line in lines)


@respx.mock
async def test_check_live_empty_wallet_and_missing_agent() -> None:
    respx.get(f"{BASE}/user/me").respond(200, json={"wallet": 0, "concurrency": {"max": 1, "current": 0}})
    respx.get(f"{BASE}/v2/agent/ag-1").respond(404, json={"message": "not found"})
    ready, lines = await check_live.check(live_settings())
    assert not ready
    assert any("wallet is empty" in line for line in lines)
    assert any("not found" in line for line in lines)


@respx.mock
async def test_check_live_bad_key() -> None:
    respx.get(f"{BASE}/user/me").respond(401, json={"error": 401, "message": "Access denied"})
    ready, lines = await check_live.check(live_settings())
    assert not ready and "rejected" in lines[0]


async def test_check_live_without_keys_explains_what_to_set() -> None:
    ready, lines = await check_live.check(Settings(_env_file=None))
    assert not ready
    assert "BOLNA_API_KEY" in lines[0]
