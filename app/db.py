"""SQLite engine and session helpers."""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, inspect, text
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
    from app.family import models as family_models  # noqa: F401

    engine = get_engine()
    SQLModel.metadata.create_all(engine)
    add_missing_columns(engine)


def add_missing_columns(engine: Engine) -> list[str]:
    """There are no migrations: `create_all` never alters an existing table, so a database made by an
    older version gets each new *nullable* column added here (ALTER TABLE ... ADD COLUMN). Returns
    the columns added, as "table.column"."""
    existing_tables = set(inspect(engine).get_table_names())
    added: list[str] = []
    with engine.begin() as conn:
        for table in SQLModel.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue
            have = {c["name"] for c in inspect(conn).get_columns(table.name)}
            for column in table.columns:
                if column.name in have or not column.nullable or column.primary_key:
                    continue
                col_type = column.type.compile(dialect=engine.dialect)
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {col_type}'))
                added.append(f"{table.name}.{column.name}")
    if added:
        from app.logs import log

        log("db_columns_added", columns=added)
    return added


def get_db() -> Iterator[DBSession]:
    with DBSession(get_engine()) as db:
        yield db


def new_db() -> DBSession:
    return DBSession(get_engine())
