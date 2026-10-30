"""Are we ready for a live call? Checks keys, wallet, concurrency, agent and webhook.

    python scripts/check_live.py
"""

from __future__ import annotations

import asyncio
import sys

import _bootstrap  # noqa: F401

from app.services.bolna_client import BolnaAuthError, BolnaClient, BolnaError, BolnaNotFound
from app.settings import Settings, get_settings


async def check(settings: Settings) -> tuple[bool, list[str]]:
    lines: list[str] = []
    ready = True

    if not settings.bolna_api_key:
        return False, [
            "BOLNA_API_KEY is missing.",
            "  1. Get a key at platform.bolna.ai > Developers > API Keys (shown only once).",
            "  2. Put BOLNA_API_KEY=... in .env.",
            "  3. Run: python scripts/create_agent.py --dry-run   (review the agent)",
            "  4. Run: python scripts/create_agent.py              (prints the agent id)",
            "  5. Put BOLNA_AGENT_ID=... in .env, set DEMO_MODE=0, then run this check again.",
        ]

    async with BolnaClient.from_settings(settings) as client:
        try:
            me = await client.get_user_me()
        except BolnaAuthError:
            return False, ["BOLNA_API_KEY was rejected (401). Check the key in .env."]
        except BolnaError as exc:
            return False, [f"Could not reach Bolna: {exc}"]
        wallet = me.get("wallet")
        conc = me.get("concurrency") or {}
        lines.append(f"OK  account: {me.get('name') or me.get('email') or me.get('id')}")
        lines.append(f"    wallet balance: {wallet}")
        lines.append(f"    concurrency: {conc.get('current')}/{conc.get('max')} calls in use")
        if isinstance(wallet, int | float) and wallet <= 0:
            ready = False
            lines.append("NO  wallet is empty: add credits before calling.")
        if conc.get("max") is not None and conc.get("current") is not None and conc["current"] >= conc["max"]:
            ready = False
            lines.append("NO  all concurrent call slots are in use.")

        if not settings.bolna_agent_id:
            ready = False
            lines.append("NO  BOLNA_AGENT_ID is missing: run python scripts/create_agent.py")
        else:
            try:
                agent = await client.get_agent(settings.bolna_agent_id)
                lines.append(f"OK  agent {settings.bolna_agent_id}: {agent.get('agent_name')!r} "
                             f"(status {agent.get('agent_status')})")
            except BolnaNotFound:
                ready = False
                lines.append(f"NO  agent {settings.bolna_agent_id} not found: run python scripts/create_agent.py")
            except BolnaError as exc:
                ready = False
                lines.append(f"NO  could not read the agent: {exc}")

    if settings.webhook_reachable:
        lines.append(f"OK  webhook: {settings.public_base_url.rstrip('/')}/api/bolna/webhook?token=***")
    else:
        lines.append("--  webhook: PUBLIC_BASE_URL is not public https, so the poller will fetch results "
                     "(every 10 s). That is fine for a local test.")
    if settings.demo_mode:
        lines.append("--  DEMO_MODE=1: the web app will still simulate calls. Set DEMO_MODE=0 for live calls.")
    return ready, lines


def main() -> int:
    ready, lines = asyncio.run(check(get_settings()))
    print("\n".join(lines))
    print("\nREADY for a live call." if ready else "\nNOT READY for a live call (see above).")
    return 0 if ready else 1


if __name__ == "__main__":
    sys.exit(main())
