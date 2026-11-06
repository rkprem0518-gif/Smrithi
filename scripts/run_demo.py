"""Serve Smriti's three apps (family, elder, care team) from ONE process, so live updates reach all three.

    python scripts/run_demo.py              # mode from .env (no .env = simulated calls until Bolna is connected)
    python scripts/run_demo.py --offline    # force offline: Bolna is never contacted, not even from the app
    python scripts/run_demo.py --open       # also open the three apps in your browser

Ports: FAMILY_PORT (8000), ELDER_PORT (8001), CLINIC_PORT (8002). The same apps are also on one address:
/smriti.html (family), /elder/ and /care/. Hosts that give a single PORT (Render, Railway) get only that one.
HOST defaults to 127.0.0.1 (use 0.0.0.0 inside Docker). Most people run `python start.py`, which sets everything
up and then runs this.
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
    if s.one_address:
        ports = {"Family": s.family_port}
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

    family = server(s.family_port, True)
    others = [] if s.one_address else [server(s.elder_port, False), server(s.clinic_port, False)]
    first = asyncio.create_task(family.serve())
    while not family.started:  # the database and sample family are ready before the other apps open
        if first.done():
            return  # startup failed; uvicorn already printed why
        await asyncio.sleep(0.1)
    rest = [asyncio.create_task(o.serve()) for o in others]
    while not all(o.started for o in others):
        await asyncio.sleep(0.1)

    base = "localhost" if host in ("127.0.0.1", "0.0.0.0") else host
    root = f"http://{base}:{s.family_port}"
    one = s.one_address
    urls = {
        "Family (start here: set up a family)": f"{root}/smriti.html",
        "Elder (the parent you add)": f"{root}/elder/" if one else f"http://{base}:{s.elder_port}/smriti.html",
        "Care team (create an account)": f"{root}/care/" if one else f"http://{base}:{s.clinic_port}/smriti.html",
    }
    if not s.demo_mode:
        mode = "LIVE: Bolna keys from .env (calls stay simulated until you turn on Real calls in the app)"
    elif s.allow_app_keys:
        mode = "Simulated calls. For real ones: Connect Bolna (paste your API key) in the family app"
    else:
        mode = "OFFLINE: Bolna is never contacted"
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
        os.environ["ALLOW_APP_KEYS"] = "0"
    if os.environ.get("PORT") and not os.environ.get("FAMILY_PORT"):
        os.environ["FAMILY_PORT"] = os.environ["PORT"]
    if any(os.environ.get(k) for k in ("RENDER", "RAILWAY_ENVIRONMENT", "DYNO", "FLY_APP_NAME")):
        # These hosts give one port: all three apps share it, under /, /elder/ and /care/.
        os.environ.setdefault("ONE_ADDRESS", "1")
    external = os.environ.get("RENDER_EXTERNAL_URL") or os.environ.get("RAILWAY_PUBLIC_DOMAIN")
    if external and not os.environ.get("PUBLIC_BASE_URL"):
        # Bolna's end-of-call webhook can reach a hosted server directly (locally the poller does the job).
        os.environ["PUBLIC_BASE_URL"] = external if external.startswith("http") else f"https://{external}"
    try:
        asyncio.run(serve(args.open))
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
