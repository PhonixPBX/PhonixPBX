# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
"""Database engine and session handling (SQLite, WAL, foreign keys on)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from phonix import config


class Base(DeclarativeBase):
    pass


_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def _on_connect(dbapi_conn: Any, _record: Any) -> None:
    # let SQLAlchemy (not the sqlite3 driver) control transactions, so that
    # SAVEPOINTs work as documented (SQLAlchemy "pysqlite" recipe)
    dbapi_conn.isolation_level = None
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.execute("PRAGMA busy_timeout=5000")
    # SQLite's lower() only folds ASCII; list searches need real case-insensitivity
    dbapi_conn.create_function("casefold", 1, lambda s: s.casefold() if isinstance(s, str) else s, deterministic=True)
    cur.close()


def _on_begin(conn: Any) -> None:
    conn.exec_driver_sql("BEGIN")


def make_engine(url: str) -> Engine:
    engine = create_engine(url, connect_args={"check_same_thread": False})
    event.listen(engine, "connect", _on_connect)
    event.listen(engine, "begin", _on_begin)
    return engine


def get_engine() -> Engine:
    global _engine, _session_factory
    if _engine is None:
        cfg = config.get()
        cfg.data_dir.mkdir(parents=True, exist_ok=True)
        _engine = make_engine(cfg.db_url)
        _session_factory = sessionmaker(_engine, expire_on_commit=False)
    return _engine


def dispose() -> None:
    """Drop the cached engine (used by tests)."""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None


def session_factory() -> sessionmaker[Session]:
    get_engine()
    assert _session_factory is not None
    return _session_factory


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional scope: commit on success, rollback on error."""
    session = session_factory()()
    try:
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()
