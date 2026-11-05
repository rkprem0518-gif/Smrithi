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


class CallOps(BaseModel):
    """Operational data about the call, copied from the Bolna execution (null until Bolna reports it).
    Amounts and latencies are in Bolna's own units. `simulated` = DEMO_MODE made the numbers up."""

    total_cost: float | None = None
    cost_breakdown: dict[str, Any] | None = None
    latency_data: dict[str, Any] | None = None
    time_to_first_audio: float | None = None
    call_duration: float | None = None
    has_recording: bool = False
    recording_url: str | None = Field(default=None, description="Only with the reviewer token")
    hangup_reason: str | None = None
    hangup_by: str | None = None
    simulated: bool = False
    updated_at: datetime | None = None


def call_ops(session: Any, include_recording: bool = False) -> CallOps:
    return CallOps(
        total_cost=session.total_cost, cost_breakdown=session.cost_breakdown, latency_data=session.latency_data,
        time_to_first_audio=session.time_to_first_audio, call_duration=session.call_duration,
        has_recording=bool(session.recording_url),
        recording_url=session.recording_url if include_recording else None,
        hangup_reason=session.hangup_reason, hangup_by=session.hangup_by,
        simulated=bool(session.ops_simulated), updated_at=session.ops_updated_at,
    )


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
    call_ops: CallOps = Field(default_factory=CallOps)


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
