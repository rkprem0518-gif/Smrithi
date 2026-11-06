"""One command to set up and run Smriti's three apps. Works on Windows, macOS and Linux.

    python start.py              # first run: makes .venv, installs packages, creates .env, starts, opens the browser
    python start.py --no-open    # same, without opening the browser
    python start.py --reset      # delete every profile first: start from the welcome screens
    python start.py --sample     # add a sample family (Appa with 8 weeks of calls) to explore
    python start.py --offline    # never contact Bolna, not even if someone pastes a key in the app

Smriti starts empty and walks you through setting up a family. No keys needed: calls are simulated until you
connect a Bolna account (Connect Bolna, under the Real calls switch). Needs Python 3.11+ (3.12 recommended).
On Windows you can also double-click start.bat.
"""

from __future__ import annotations

import os
import re
import secrets
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
PY = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
SECRETS = ("SECRET_SALT", "ADMIN_REVIEW_TOKEN", "BOLNA_WEBHOOK_TOKEN")


def run(*cmd: str) -> None:
    subprocess.run(cmd, cwd=ROOT, check=True)


def make_env(env_file: Path) -> None:
    """Copy .env.example and give it its own random secrets (they sign logins and hash phone numbers)."""
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    for key in SECRETS:
        text = re.sub(rf"^{key}=change-me", f"{key}={secrets.token_urlsafe(24)}", text, flags=re.M)
    env_file.write_text(text, encoding="utf-8")
    print("Created .env (calls are simulated until you connect Bolna in the app).", flush=True)


def main() -> int:
    if sys.version_info < (3, 11):  # noqa: UP036  (a reviewer may run this with an older Python)
        print(f"Smriti needs Python 3.11 or newer; this is {sys.version.split()[0]}.", flush=True)
        print("Install Python 3.12 from python.org, then run: python start.py", flush=True)
        return 1
    if not PY.exists():
        print("Creating a virtual environment in .venv ...", flush=True)
        venv.EnvBuilder(with_pip=True).create(VENV)
    stamp = VENV / ".smriti-installed"
    req = ROOT / "requirements.txt"
    if not stamp.exists() or stamp.stat().st_mtime < req.stat().st_mtime:
        print("Installing packages (first run takes a minute) ...", flush=True)
        try:
            run(str(PY), "-m", "pip", "install", "--disable-pip-version-check", "-q", "-r", str(req))
        except subprocess.CalledProcessError:
            print("\nInstalling packages failed (see above). Check your internet connection and run again.", flush=True)
            return 1
        stamp.touch()
    env_file = ROOT / ".env"
    if not env_file.exists():
        make_env(env_file)
    args = sys.argv[1:]
    for flag, script_flag in (("--reset", "--empty"), ("--sample", "--sample")):
        if flag in args:
            args.remove(flag)
            run(str(PY), "scripts/seed_family.py", script_flag)
    if "--no-open" in args:
        args.remove("--no-open")
    elif "--open" not in args and not os.environ.get("CI"):
        args.append("--open")
    try:
        return subprocess.run([str(PY), "scripts/run_demo.py", *args], cwd=ROOT).returncode
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
