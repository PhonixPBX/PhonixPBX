# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
"""Run Alembic migrations without an alembic.ini on disk."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import Connection, inspect, text

from phonix.core.db import get_engine

if TYPE_CHECKING:
    from alembic.config import Config

# alembic (and mako) are only imported to actually migrate: the web process
# checks needs_upgrade() on startup and must not carry them (~10 MB)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"

# Pre-1.0 nightly revisions folded into 0001 whose schema equals it. Can be dropped after 1.x.
SQUASHED_REVISIONS = {"0003": "0001"}


def alembic_config() -> Config:
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    return cfg


def upgrade(revision: str = "head") -> None:
    from alembic import command

    cfg = alembic_config()
    with get_engine().begin() as conn:
        cfg.attributes["connection"] = conn
        _restamp_squashed(conn)
        command.upgrade(cfg, revision)


def _restamp_squashed(conn: Connection) -> None:
    current = _revision(conn)
    if current in SQUASHED_REVISIONS:
        conn.execute(text("UPDATE alembic_version SET version_num = :new"), {"new": SQUASHED_REVISIONS[current]})


def _revision(conn: Connection) -> str | None:
    if not inspect(conn).has_table("alembic_version"):
        return None
    return conn.scalar(text("SELECT version_num FROM alembic_version"))


def current_revision() -> str | None:
    with get_engine().connect() as conn:
        return _revision(conn)


_REVISION_RE = re.compile(r'^(down_revision|revision)\s*=\s*(?:"([^"]+)"|None)', re.M)


def head_revision() -> str | None:
    """The newest revision of the (linear) history, without loading alembic."""
    revisions: set[str] = set()
    parents: set[str] = set()
    for path in (MIGRATIONS_DIR / "versions").glob("*.py"):
        for key, value in _REVISION_RE.findall(path.read_text()):
            if value:
                (revisions if key == "revision" else parents).add(value)
    heads = revisions - parents
    if len(heads) > 1:
        raise RuntimeError(f"multiple migration heads: {sorted(heads)}")
    return heads.pop() if heads else None


def needs_upgrade() -> bool:
    return current_revision() != head_revision()
