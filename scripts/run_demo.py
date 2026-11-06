"""Serve Smriti's three apps (family, elder, care team) from ONE process, so live updates reach all three.

    python scripts/run_demo.py              # mode from .env (no .env = offline: simulated calls, no keys)
    python scripts/run_demo.py --offline    # force offline, even if .env has Bolna keys
    python scripts/run_demo.py --open       # also open the three apps in your browser

Ports: FAMILY_PORT (8000), ELDER_PORT (8001), CLINIC_PORT (8002). HOST defaults to 127.0.0.1 (use 0.0.0.0
inside Docker). Most people start with `python start.py`, which sets everything up and then runs this.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import socket
import sys
import webbrowser

import _bootstrap  # noqa: F401


def port_is_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
        except OSError:
            return False
        return True


async def serve(open_browser: bool) -> None:
    import uvicorn

    from app.main import app
    from app.settings import get_settings

    s = get_settings()
    host = os.environ.get("HOST", "127.0.0.1")
    ports = {"Family": s.family_port, "Elder": s.elder_port, "Care team": s.clinic_port}
    busy = [f"{name} :{port}" for name, port in ports.items() if not port_is_free(host, port)]
    if busy:
        print(f"\nThese ports are already in use: {', '.join(busy)}.")
        print("Close the other Smriti window (or whatever uses them), or choose other ports in .env:")
        print("  FAMILY_PORT=9000  ELDER_PORT=9001  CLINIC_PORT=9002\n")
        sys.exit(1)

    def server(port: int, first: bool) -> uvicorn.Server:
        # Only the first server runs startup (database, sample family, poller); the others just serve requests.
        return uvicorn.Server(uvicorn.Config(app, host=host, port=port, lifespan="on" if first else "off",
                                             log_level="info" if first else "warning"))

    family, elder, clinic = server(s.family_port, True), server(s.elder_port, False), server(s.clinic_port, False)
    first = asyncio.create_task(family.serve())
    while not family.started:  # the database and sample family are ready before the other apps open
        if first.done():
            return  # startup failed; uvicorn already printed why
        await asyncio.sleep(0.1)
    rest = [asyncio.create_task(elder.serve()), asyncio.create_task(clinic.serve())]
    while not (elder.started and clinic.started):
        await asyncio.sleep(0.1)

    base = "localhost" if host in ("127.0.0.1", "0.0.0.0") else host
    urls = {
        "Family (log in as Ravi or Priya)": f"http://{base}:{s.family_port}/smriti.html",
        "Elder (log in as Appa)": f"http://{base}:{s.elder_port}/smriti.html",
        "Care team (log in as Dr. Meera)": f"http://{base}:{s.clinic_port}/smriti.html",
    }
    mode = "OFFLINE: calls are simulated, no Bolna credits" if s.demo_mode else \
        "LIVE: Bolna connected (calls stay simulated until you turn on Real calls in the app)"
    print("\n  Smriti is running  ·  " + mode)
    for label, url in urls.items():
        print(f"    {label:<34} {url}")
    print("  Press Ctrl+C to stop.\n")
    if open_browser:
        for url in urls.values():
            webbrowser.open_new_tab(url)
    await asyncio.gather(first, *rest)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--offline", action="store_true", help="simulated calls only; Bolna is never contacted")
    parser.add_argument("--open", action="store_true", help="open the three apps in your browser")
    args = parser.parse_args()
    if args.offline:
        os.environ["DEMO_MODE"] = "1"  # read by the settings, before the app is imported
    if os.environ.get("PORT") and not os.environ.get("FAMILY_PORT"):
        os.environ["FAMILY_PORT"] = os.environ["PORT"]  # hosts like Render give one port: the family app takes it
    try:
        asyncio.run(serve(args.open))
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
