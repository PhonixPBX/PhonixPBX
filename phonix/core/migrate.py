# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
"""Run Alembic migrations without an alembic.ini on disk."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, text

from phonix.core.db import get_engine

MIGRATIONS_DIR = Path(__file__).parent / "migrations"

# Pre-1.0 nightly revisions folded into 0001 whose schema equals it. Can be dropped after 1.x.
SQUASHED_REVISIONS = {"0003": "0001"}


def alembic_config() -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    return cfg


def upgrade(revision: str = "head") -> None:
    cfg = alembic_config()
    with get_engine().begin() as conn:
        cfg.attributes["connection"] = conn
        _restamp_squashed(conn)
        command.upgrade(cfg, revision)


def _restamp_squashed(conn: Connection) -> None:
    current = MigrationContext.configure(conn).get_current_revision()
    if current in SQUASHED_REVISIONS:
        conn.execute(text("UPDATE alembic_version SET version_num = :new"), {"new": SQUASHED_REVISIONS[current]})


def current_revision() -> str | None:
    with get_engine().connect() as conn:
        return MigrationContext.configure(conn).get_current_revision()


def head_revision() -> str | None:
    return ScriptDirectory.from_config(alembic_config()).get_current_head()


def needs_upgrade() -> bool:
    return current_revision() != head_revision()
