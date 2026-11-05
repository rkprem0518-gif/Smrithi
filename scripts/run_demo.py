"""Serve Smriti on three ports from ONE process, so all three apps share the same live updates.

    python scripts/run_demo.py            # family :8000, elder :8001, clinic :8002 (ports from .env)

Open each in its own browser window and log in with the demo button. Anything done in one app (a call,
a review, someone joining the circle) appears in the others within a second.
"""

from __future__ import annotations

import asyncio

import _bootstrap  # noqa: F401
import uvicorn

from app.main import app
from app.settings import get_settings


async def main() -> None:
    s = get_settings()
    servers = []
    for i, port in enumerate((s.family_port, s.elder_port, s.clinic_port)):
        # Only the first server runs startup/shutdown (database, seed, poller); the others just serve requests.
        config = uvicorn.Config(
            app,
            host="127.0.0.1",
            port=port,
            lifespan="on" if i == 0 else "off",
            log_level="info" if i == 0 else "warning",
        )
        servers.append(uvicorn.Server(config))
    print(f"Family  http://localhost:{s.family_port}/smriti.html")
    print(f"Elder   http://localhost:{s.elder_port}/")
    print(f"Clinic  http://localhost:{s.clinic_port}/")
    await servers[0].serve() if len(servers) == 1 else await asyncio.gather(*(srv.serve() for srv in servers))


if __name__ == "__main__":
    asyncio.run(main())
