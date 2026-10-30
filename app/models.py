"""Database tables. Phone numbers are never stored: only a salted hash and the last 4 digits."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


class Status:
    CREATED = "created"
    DECLINED = "declined"
    CALLING = "calling"
    IN_PROGRESS = "in_progress"
    CALL_ENDED = "call_ended"
    SCORING = "scoring"
    SCORED = "scored"
    NO_ANSWER = "no_answer"
    BUSY = "busy"
    FAILED = "failed"
    STOPPED = "stopped"
    INVALID = "invalid"

    OPEN = (CALLING, IN_PROGRESS, CALL_ENDED)
    FINAL = (DECLINED, SCORED, NO_ANSWER, BUSY, FAILED, STOPPED, INVALID)


class ReviewStatus:
    NOT_NEEDED = "not_needed"
    PENDING = "pending"
    REVIEWED = "reviewed"


class Session(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    mode: str = "phone"  # phone | web
    language: str = "hi"  # hi | en
    schooling_years: int | None = None
    schooling_band: str | None = None  # LOW | HIGH
    word_form: str = "A"  # A | B | C
    consent_ui: bool = False
    consent_call: bool | None = None
    phone_hash: str | None = None
    phone_last4: str | None = None
    ip_hash: str | None = Field(default=None, index=True)
    execution_id: str | None = Field(default=None, index=True)
    status: str = Field(default=Status.CREATED, index=True)
    review_status: str = Field(default=ReviewStatus.NOT_NEEDED, index=True)
    is_demo: bool = False
    error: str | None = None
    deleted_at: datetime | None = None


class CallArtifact(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    session_id: str = Field(foreign_key="session.id", index=True)
    transcript_json: list[dict[str, Any]] | None = Field(default=None, sa_column=Column(JSON))
    recording_url: str | None = None
    execution_json_redacted: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    fetched_at: datetime = Field(default_factory=utcnow)


class Score(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    session_id: str = Field(foreign_key="session.id", index=True)
    created_at: datetime = Field(default_factory=utcnow)
    scorer_version: str
    hearing: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    learning_trials: list[Any] = Field(default_factory=list, sa_column=Column(JSON))
    learning_total: int = 0
    fluency_count: int = 0
    fluency_words: list[Any] = Field(default_factory=list, sa_column=Column(JSON))
    orientation: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    orientation_total: int = 0
    delayed_recall: int = 0
    delayed_words: list[Any] = Field(default_factory=list, sa_column=Column(JSON))
    invalid_reasons: list[Any] = Field(default_factory=list, sa_column=Column(JSON))
    outcome: str
    rule_fired: str
    band: str | None = None
    speech_markers: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    report_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


class Review(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    session_id: str = Field(foreign_key="session.id", index=True)
    reviewer: str
    decision: str  # agree | override_normal | override_refer | retest
    note: str = ""
    created_at: datetime = Field(default_factory=utcnow)
