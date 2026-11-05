"""Create (or update) the Smriti agent on Bolna and print its agent_id.

    python scripts/create_agent.py --dry-run      # print the exact JSON payload; no API call, no key needed
    python scripts/create_agent.py                # POST /v2/agent -> prints agent_id
    python scripts/create_agent.py --update       # PUT /v2/agent/{BOLNA_AGENT_ID}
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

import _bootstrap  # noqa: F401

from app.config_loader import agent_prompt, agent_template, scoring_config
from app.services.agent_builder import build_agent_payload
from app.services.bolna_client import BolnaClient, BolnaError
from app.settings import get_settings


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="print the payload and exit")
    parser.add_argument("--update", action="store_true", help="update the existing agent (PUT)")
    parser.add_argument("--agent-id", default=None, help="agent to update (default: BOLNA_AGENT_ID)")
    parser.add_argument("--multilingual", action="store_true",
                        help="one agent for Hindi, Kannada and English that asks which language to speak "
                             "(BOLNA_AGENT_ID; set BOLNA_MULTILINGUAL=1)")
    parser.add_argument("--language", choices=["hi", "kn", "en"], default="hi",
                        help="hi = BOLNA_AGENT_ID, kn = BOLNA_AGENT_ID_KN, en = BOLNA_AGENT_ID_EN")
    parser.add_argument("--with-keywords", action="store_true",
                        help="add the 30 list words as transcriber keywords (format unverified, see TODO)")
    args = parser.parse_args()

    settings = get_settings()
    payload = build_agent_payload(settings, agent_template(), agent_prompt(), scoring_config(), args.with_keywords,
                                  language=args.language, multilingual=args.multilingual)
    env_key = {"kn": "BOLNA_AGENT_ID_KN", "en": "BOLNA_AGENT_ID_EN"}.get(args.language, "BOLNA_AGENT_ID")

    if args.dry_run:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        note = "" if settings.webhook_reachable else "  (PUBLIC_BASE_URL is not public https -> poller is used)"
        print(f"\n# dry run: nothing was sent. webhook_url = {payload['agent_config'].get('webhook_url')!r}{note}",
              file=sys.stderr)
        return 0

    if not settings.bolna_api_key:
        print("BOLNA_API_KEY is not set in .env. Use --dry-run to review the payload without a key.", file=sys.stderr)
        return 2
    try:
        async with BolnaClient.from_settings(settings) as client:
            if args.update:
                # Only this language's own agent: never fall back, or an update could overwrite another language.
                agent_id = args.agent_id or getattr(settings, env_key.lower())
                if not agent_id:
                    print(f"--update needs {env_key} in .env or --agent-id.", file=sys.stderr)
                    return 2
                result = await client.update_agent(agent_id, payload)
                print(f"Updated agent {agent_id}: {result}")
            else:
                agent_id = await client.create_agent(payload)
                print(agent_id)
                print(f"\nCreated. Add this line to .env:\n{env_key}={agent_id}", file=sys.stderr)
    except BolnaError as exc:
        print(f"Bolna error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
