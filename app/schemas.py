"""Request/response models for the REST API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class SessionCreate(BaseModel):
    consent: bool
    language: Literal["hi", "en", "kn"] = "hi"
    schooling_years: int | None = Field(default=None, ge=0, le=30)
    mode: Literal["phone", "web"] = "phone"
    phone: str | None = Field(default=None, max_length=20)
    demo_fixture: str | None = Field(default=None, description="DEMO_MODE only: which fixture to simulate")


class SessionCreated(BaseModel):
    session_id: str
    status: str
    demo: bool
    web_call: dict[str, Any] | None = None


class SessionOut(BaseModel):
    session_id: str
    status: str
    review_status: str
    mode: str
    language: str
    created_at: datetime
    is_demo: bool
    outcome: str | None = None
    report: dict[str, Any] | None = None
    error: str | None = None


class TurnIn(BaseModel):
    role: Literal["assistant", "agent", "user"]
    text: str
    t: float | None = None


class DemoScoreRequest(BaseModel):
    transcript: list[TurnIn] | str = Field(description="Turns, or a Bolna transcript string")
    language: Literal["hi", "en", "kn"] = "hi"
    schooling_years: int | None = Field(default=None, ge=0, le=30)
    word_form: Literal["A", "B", "C"] = "A"
    call_time: datetime | None = Field(default=None, description="Defaults to now (IST used for orientation)")


class ReviewDecision(BaseModel):
    reviewer: str = Field(min_length=1, max_length=80)
    decision: Literal["agree", "override_normal", "override_refer", "retest"]
    note: str = Field(default="", max_length=2000)
