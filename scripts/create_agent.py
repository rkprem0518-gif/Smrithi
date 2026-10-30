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
    parser.add_argument("--with-keywords", action="store_true",
                        help="add the 30 list words as transcriber keywords (format unverified, see TODO)")
    args = parser.parse_args()

    settings = get_settings()
    payload = build_agent_payload(settings, agent_template(), agent_prompt(), scoring_config(), args.with_keywords)

    if args.dry_run:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        note = "" if settings.webhook_reachable else "  (PUBLIC_BASE_URL is not public https -> poller is used)"
        print(f"\n# dry run: nothing was sent. webhook_url = {payload['agent_config']['webhook_url']!r}{note}",
              file=sys.stderr)
        return 0

    if not settings.bolna_api_key:
        print("BOLNA_API_KEY is not set in .env. Use --dry-run to review the payload without a key.", file=sys.stderr)
        return 2
    try:
        async with BolnaClient.from_settings(settings) as client:
            if args.update:
                agent_id = args.agent_id or settings.bolna_agent_id
                if not agent_id:
                    print("--update needs BOLNA_AGENT_ID in .env or --agent-id.", file=sys.stderr)
                    return 2
                result = await client.update_agent(agent_id, payload)
                print(f"Updated agent {agent_id}: {result}")
            else:
                agent_id = await client.create_agent(payload)
                print(agent_id)
                print(f"\nCreated. Add this line to .env:\nBOLNA_AGENT_ID={agent_id}", file=sys.stderr)
    except BolnaError as exc:
        print(f"Bolna error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
