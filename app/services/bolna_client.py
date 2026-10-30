"""Async client for the Bolna REST API (https://www.bolna.ai/docs, checked 2026-10-30).

Endpoints used:
  POST /v2/agent                 create agent        -> {"agent_id", "state", "version_id"}
  PUT  /v2/agent/{agent_id}      replace agent       -> {"agent_id", "status": "updated"}
  GET  /v2/agent/{agent_id}      read agent          -> {"id", "agent_name", ...}
  POST /call                     place outbound call -> {"message", "status": "queued", "execution_id"}
  GET  /executions/{id}          call status + transcript (string) + telephony_data.recording_url
  GET  /user/me                  {"id", "name", "email", "wallet", "concurrency": {"max", "current"}}
  POST /web-call/session         single-use Web Call SDK session (expires ~120 s)

Retries: 3 retries with exponential backoff on 5xx and network errors; never on 4xx.
Only paths and status codes are logged - never request bodies (they hold phone numbers).
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.logs import log
from app.settings import Settings

# Execution statuses after which nothing changes (docs list + "stopped").
FINAL_STATUSES = frozenset(
    {"completed", "no-answer", "busy", "failed", "canceled", "stopped", "error", "balance-low"}
)


class BolnaError(Exception):
    def __init__(self, message: str, status_code: int | None = None, body: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class BolnaAuthError(BolnaError):
    """401/403: missing or wrong BOLNA_API_KEY."""


class BolnaNotFound(BolnaError):
    """404: unknown agent or execution id."""


class BolnaRateLimited(BolnaError):
    """429: e.g. a newly bought from-number is still warming up."""

    def __init__(self, message: str, retry_after: float | None, body: Any = None) -> None:
        super().__init__(message, 429, body)
        self.retry_after = retry_after


class BolnaClientError(BolnaError):
    """Any other 4xx: the request itself is wrong (not retried)."""


class BolnaServerError(BolnaError):
    """5xx after all retries."""


class BolnaNetworkError(BolnaError):
    """Timeout / connection error after all retries."""


def _error_message(resp: httpx.Response) -> tuple[str, Any]:
    try:
        body = resp.json()
    except ValueError:
        body = resp.text[:300]
    msg = body.get("message") if isinstance(body, dict) else None
    return f"Bolna {resp.request.method} {resp.request.url.path} -> {resp.status_code}: {msg or body}", body


class BolnaClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.bolna.ai",
        timeout: float = 15.0,
        retries: int = 3,
        backoff: float = 0.5,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise BolnaAuthError("BOLNA_API_KEY is not set")
        self.retries = retries
        self.backoff = backoff
        self._http = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            transport=transport,
        )

    @classmethod
    def from_settings(cls, settings: Settings) -> BolnaClient:
        return cls(
            api_key=settings.bolna_api_key,
            base_url=settings.bolna_api_base,
            timeout=settings.bolna_timeout_seconds,
            backoff=settings.bolna_retry_backoff_seconds,
        )

    async def __aenter__(self) -> BolnaClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        last_exc: BolnaError | None = None
        for attempt in range(self.retries + 1):
            if attempt:
                await asyncio.sleep(self.backoff * 2 ** (attempt - 1))
            try:
                resp = await self._http.request(method, path, **kwargs)
            except httpx.TransportError as exc:  # includes timeouts
                last_exc = BolnaNetworkError(f"Bolna {method} {path}: {type(exc).__name__}")
                log("bolna_network_error", method=method, path=path, attempt=attempt)
                continue
            log("bolna_response", method=method, path=path, status=resp.status_code, attempt=attempt)
            if resp.status_code >= 500:
                msg, body = _error_message(resp)
                last_exc = BolnaServerError(msg, resp.status_code, body)
                continue
            if resp.status_code >= 400:
                msg, body = _error_message(resp)
                if resp.status_code in (401, 403):
                    raise BolnaAuthError(msg, resp.status_code, body)
                if resp.status_code == 404:
                    raise BolnaNotFound(msg, 404, body)
                if resp.status_code == 429:
                    retry_after = body.get("retry_after_seconds") if isinstance(body, dict) else None
                    raise BolnaRateLimited(msg, retry_after, body)
                raise BolnaClientError(msg, resp.status_code, body)
            if not resp.content:
                return {}
            try:
                return resp.json()
            except ValueError as exc:
                raise BolnaServerError(f"Bolna {method} {path}: response was not JSON") from exc
        assert last_exc is not None
        raise last_exc

    # ------------------------------------------------------------------ agents

    async def create_agent(self, payload: dict[str, Any]) -> str:
        data = await self._request("POST", "/v2/agent", json=payload)
        agent_id = data.get("agent_id") or data.get("id")
        if not agent_id:
            raise BolnaServerError("Bolna create agent: no agent_id in response", body=data)
        return str(agent_id)

    async def update_agent(self, agent_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request("PUT", f"/v2/agent/{agent_id}", json=payload)

    async def patch_agent(self, agent_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request("PATCH", f"/v2/agent/{agent_id}", json=payload)

    async def get_agent(self, agent_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/v2/agent/{agent_id}")

    # ------------------------------------------------------------------ calls

    async def make_call(
        self,
        agent_id: str,
        recipient_phone_number: str,
        user_data: dict[str, Any] | None = None,
        from_phone_number: str | None = None,
    ) -> str:
        payload: dict[str, Any] = {"agent_id": agent_id, "recipient_phone_number": recipient_phone_number}
        if from_phone_number:
            payload["from_phone_number"] = from_phone_number
        if user_data:
            payload["user_data"] = user_data
        data = await self._request("POST", "/call", json=payload)
        execution_id = data.get("execution_id")
        if not execution_id:
            raise BolnaServerError("Bolna make call: no execution_id in response", body=data)
        return str(execution_id)

    async def get_execution(self, execution_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/executions/{execution_id}")

    async def create_web_call_session(
        self, agent_id: str, user_data: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Mint a single-use session for @bolna/web-call (the browser never sees our API key)."""
        payload: dict[str, Any] = {"agent_id": agent_id}
        if user_data:
            payload["user_data"] = user_data
        return await self._request("POST", "/web-call/session", json=payload)

    # ------------------------------------------------------------------ account

    async def get_user_me(self) -> dict[str, Any]:
        return await self._request("GET", "/user/me")
