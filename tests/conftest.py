from __future__ import annotations

import os
from datetime import datetime

import pytest

# Tests never read the developer's .env and never touch the real database.
os.environ.setdefault("DEMO_MODE", "1")
os.environ["DATABASE_URL"] = "sqlite://"  # replaced per test by the `app_env` fixture

from app.config_loader import scoring_config  # noqa: E402
from app.scoring.types import ScoringConfig, Turn  # noqa: E402


@pytest.fixture(scope="session")
def cfg() -> ScoringConfig:
    return scoring_config()


@pytest.fixture
def call_time() -> datetime:
    # Wednesday 28 Oct 2026, 10:15 IST
    return datetime.fromisoformat("2026-10-28T10:15:00+05:30")


def agent(text: str) -> Turn:
    return Turn("agent", text)


def user(text: str) -> Turn:
    return Turn("user", text)
