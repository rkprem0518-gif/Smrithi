"""(Re)create the demo parent "Appa" with eight weeks of history.

    python scripts/seed_family.py           # only if missing
    python scripts/seed_family.py --reset   # wipe Appa's data and start fresh (run right before a demo)
"""

import argparse

import _bootstrap  # noqa: F401

from app.db import init_db, new_db
from app.family import seed
from app.settings import get_settings

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()
    init_db()
    with new_db() as db:
        parent = seed.seed(db, get_settings(), reset=args.reset)
        print(f"Parent {parent.call_name} ({parent.id}) ready. Open http://localhost:8000/smriti.html")
