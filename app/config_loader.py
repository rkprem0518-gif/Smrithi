"""Loads config/*.yaml and config/agent.json once (file I/O lives here, not in scoring/)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.scoring.types import ScoringConfig

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
PROMPTS_DIR = ROOT / "prompts"
FIXTURES_DIR = ROOT / "fixtures"


def _yaml(name: str) -> dict[str, Any]:
    with open(CONFIG_DIR / name, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@lru_cache
def scoring_config() -> ScoringConfig:
    return ScoringConfig.from_dicts(
        _yaml("scoring.yaml"), _yaml("wordlists.yaml"), _yaml("animals.yaml")
    )


@lru_cache
def agent_template() -> dict[str, Any]:
    with open(CONFIG_DIR / "agent.json", encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache
def animal_hindi_names() -> dict[str, str]:
    groups = _yaml("animals.yaml")["animals"]
    return {
        name: next((v for v in variants if any("\u0900" <= ch <= "\u097f" for ch in str(v))), name)
        for name, variants in groups.items()
    }


def markers() -> dict[str, list[str]]:
    return agent_template()["smriti_markers"]


def agent_prompt() -> str:
    return (PROMPTS_DIR / "smriti_agent.md").read_text(encoding="utf-8")


def load_fixture(name: str) -> dict[str, Any]:
    with open(FIXTURES_DIR / f"{name}.json", encoding="utf-8") as fh:
        return json.load(fh)


FIXTURE_NAMES = ("normal", "uncertain", "refer", "invalid_hearing", "kannada")
