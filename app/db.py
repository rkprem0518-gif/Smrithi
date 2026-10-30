"""SQLite engine and session helpers."""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine
from sqlmodel import Session as DBSession
from sqlmodel import SQLModel, create_engine

from app.settings import get_settings


@lru_cache
def get_engine() -> Engine:
    url = get_settings().database_url
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args)


def init_db() -> None:
    from app import models  # noqa: F401  (registers the tables)

    SQLModel.metadata.create_all(get_engine())


def get_db() -> Iterator[DBSession]:
    with DBSession(get_engine()) as db:
        yield db


def new_db() -> DBSession:
    return DBSession(get_engine())
