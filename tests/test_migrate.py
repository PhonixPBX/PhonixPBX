# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import text

from phonix import config
from phonix.core import db, migrate
from phonix.core.models import Base


def test_migrations_match_models(runtime: config.RuntimeConfig) -> None:
    migrate.upgrade()
    with db.get_engine().connect() as conn:
        assert compare_metadata(MigrationContext.configure(conn), Base.metadata) == []


def test_squashed_nightly_revision_is_restamped(runtime: config.RuntimeConfig) -> None:
    migrate.upgrade()
    with db.get_engine().begin() as conn:
        conn.execute(text("UPDATE alembic_version SET version_num = '0003'"))
    migrate.upgrade()
    assert migrate.current_revision() == migrate.head_revision() == "0001"
    assert not migrate.needs_upgrade()
