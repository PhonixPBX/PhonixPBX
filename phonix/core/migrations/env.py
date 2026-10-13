# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
"""Alembic environment: uses the connection handed over by phonix.core.migrate."""

from __future__ import annotations

from alembic import context

from phonix.core import models  # noqa: F401  (register tables)
from phonix.core.db import Base

target_metadata = Base.metadata


def run_migrations_online() -> None:
    connection = context.config.attributes.get("connection")
    if connection is None:
        from phonix.core.db import get_engine

        with get_engine().connect() as conn:
            _run(conn)
            conn.commit()
    else:
        _run(connection)


def _run(connection) -> None:  # type: ignore[no-untyped-def]
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,  # SQLite needs batch mode for ALTER TABLE
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


run_migrations_online()
