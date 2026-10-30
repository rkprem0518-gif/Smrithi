"""(Re)seed the 4 offline demo sessions, scored by the real engine.

    python scripts/seed_demo.py
"""

import _bootstrap  # noqa: F401

from app.db import init_db
from app.services.orchestrator import seed_demo_sessions
from app.settings import get_settings

if __name__ == "__main__":
    init_db()
    for sid in seed_demo_sessions(get_settings()):
        print(f"seeded {sid}  ->  /report.html?id={sid}")
