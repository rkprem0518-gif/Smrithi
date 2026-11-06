"""Profiles on this machine: start empty, or add the sample family.

    python scripts/seed_family.py --empty    # delete every profile and account (fresh start, welcome screens)
    python scripts/seed_family.py --sample   # add the sample family: Appa with 8 weeks of calls, Ravi, Priya, Dr. Meera
    python scripts/seed_family.py --reset    # rebuild the sample family from scratch
"""

import argparse

import _bootstrap  # noqa: F401

from app.db import init_db, new_db
from app.family import people, seed
from app.settings import get_settings

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--empty", action="store_true", help="delete every profile and account")
    parser.add_argument("--sample", action="store_true", help="add the sample family")
    parser.add_argument("--reset", action="store_true", help="rebuild the sample family from scratch")
    args = parser.parse_args()
    init_db()
    with new_db() as db:
        if args.empty:
            removed = people.start_over(db)
            print(f"Removed {removed} profile(s) and every account. Smriti starts at the welcome screen.")
        elif args.sample or args.reset:
            parent = seed.seed(db, get_settings(), reset=args.reset)
            print(f"Sample family ready: {parent.call_name}. Open http://localhost:8000/smriti.html")
        else:
            parser.print_help()
