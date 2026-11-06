"""One command to set up and run Smriti's three apps. Works on Windows, macOS and Linux.

    python start.py            # first run: makes .venv, installs packages, creates .env, then starts
    python start.py --open     # same, and opens the three apps in your browser
    python start.py --reset    # fresh sample family before starting (good right before a demo)

No keys needed: without Bolna keys every call is simulated. Needs Python 3.11+ (3.12 recommended).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
PY = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def run(*cmd: str) -> None:
    subprocess.run(cmd, cwd=ROOT, check=True)


def main() -> int:
    if sys.version_info < (3, 11):  # noqa: UP036  (a reviewer may run this with an older Python)
        print(f"Smriti needs Python 3.11 or newer; this is {sys.version.split()[0]}. Install 3.12 from python.org.")
        return 1
    if not PY.exists():
        print("Creating a virtual environment in .venv ...")
        venv.EnvBuilder(with_pip=True).create(VENV)
    stamp = VENV / ".smriti-installed"
    req = ROOT / "requirements.txt"
    if not stamp.exists() or stamp.stat().st_mtime < req.stat().st_mtime:
        print("Installing packages (first run takes a minute) ...")
        run(str(PY), "-m", "pip", "install", "--disable-pip-version-check", "-q", "-r", str(req))
        stamp.touch()
    env_file = ROOT / ".env"
    if not env_file.exists():
        shutil.copy(ROOT / ".env.example", env_file)
        print("Created .env from .env.example (offline mode: calls are simulated, no keys needed).")
    args = sys.argv[1:]
    if "--reset" in args:
        args.remove("--reset")
        run(str(PY), "scripts/seed_family.py", "--reset")
    try:
        return subprocess.run([str(PY), "scripts/run_demo.py", *args], cwd=ROOT).returncode
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
