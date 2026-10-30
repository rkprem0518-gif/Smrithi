"""Call a phone number with the Smriti agent, wait for the result and print the report.

    python scripts/test_call.py +919876543210 [--language hi|en] [--schooling 8] [--timeout 15]

Runs the same pipeline as the web app (session -> POST /call -> poll GET /executions/{id}
-> segment -> score), so it needs DEMO_MODE=0, BOLNA_API_KEY and BOLNA_AGENT_ID.
The number is used only to place the call; only a salted hash and the last 4 digits are stored.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time

import _bootstrap  # noqa: F401
from sqlmodel import select

from app.db import init_db, new_db
from app.models import Score, Session, Status
from app.services import orchestrator
from app.services.bolna_client import BolnaClient
from app.settings import LiveConfigError, get_settings


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("phone", help="E.164 number, e.g. +919876543210")
    parser.add_argument("--language", choices=["hi", "en"], default="hi")
    parser.add_argument("--schooling", type=int, default=None)
    parser.add_argument("--timeout", type=float, default=15, help="minutes to wait")
    args = parser.parse_args()

    settings = get_settings()
    if settings.demo_mode:
        print("DEMO_MODE=1: set DEMO_MODE=0 in .env for a real call.", file=sys.stderr)
        return 2
    try:
        settings.require_live()
    except LiveConfigError as exc:
        print(exc, file=sys.stderr)
        return 2
    init_db()

    with new_db() as db:
        try:
            session, _ = await orchestrator.create_session(
                db, consent=True, language=args.language, mode="phone", schooling_years=args.schooling,
                phone=args.phone, client_ip="cli", settings=settings,
            )
        except orchestrator.SessionError as exc:
            print(f"Could not start: {exc}", file=sys.stderr)
            return 1
        session_id = session.id
    print(f"session {session_id}  form {session.word_form}  execution {session.execution_id}")

    deadline = time.monotonic() + args.timeout * 60
    last = None
    async with BolnaClient.from_settings(settings) as client:
        while time.monotonic() < deadline:
            with new_db() as db:
                session = db.get(Session, session_id)
                assert session is not None
                if session.status != last:
                    print(f"  status: {session.status}")
                    last = session.status
                if session.status in Status.FINAL:
                    break
                execution = await client.get_execution(session.execution_id or "")
                await orchestrator.apply_execution(db, session, execution, settings)
            await asyncio.sleep(settings.poll_interval_seconds)

    with new_db() as db:
        session = db.get(Session, session_id)
        score = db.exec(select(Score).where(Score.session_id == session_id)).first()
        print(f"\nfinal status: {session.status if session else '?'}  error: {session.error if session else ''}")
        if score:
            r = score.report_json
            print(f"OUTCOME: {r['outcome']}  ({r['rule_fired']})")
            print(json.dumps(r["domains"], ensure_ascii=False, indent=2))
            print(f"\nReport page: {settings.public_base_url.rstrip('/')}/report.html?id={session_id}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
