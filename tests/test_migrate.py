# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text

from phonix import config
from phonix.core import db, migrate
from phonix.core.models import Base


def test_migrations_match_models(runtime: config.RuntimeConfig) -> None:
    migrate.upgrade()
    with db.get_engine().connect() as conn:
        assert compare_metadata(MigrationContext.configure(conn), Base.metadata) == []


def test_head_revision_matches_alembic() -> None:
    assert migrate.head_revision() == ScriptDirectory.from_config(migrate.alembic_config()).get_current_head()


def test_squashed_nightly_revision_is_restamped(runtime: config.RuntimeConfig) -> None:
    # a pre-1.0 nightly database at 0003 has the schema of 0001
    migrate.upgrade("0001")
    with db.get_engine().begin() as conn:
        conn.execute(text("UPDATE alembic_version SET version_num = '0003'"))
    migrate.upgrade()
    assert migrate.current_revision() == migrate.head_revision() == "0008"
    assert not migrate.needs_upgrade()


def test_0004_moves_custom_voicemail_text(runtime: config.RuntimeConfig) -> None:
    import json

    migrate.upgrade("0001")
    with db.get_engine().begin() as conn:
        conn.execute(
            text("INSERT INTO settings (\"group\", data) VALUES ('system', :s), ('voicemail', :v)"),
            {
                "s": json.dumps({"prompt_language": "fr"}),
                "v": json.dumps({"from_name": "VM", "custom_subject": "Nouveau", "custom_body": "Bonjour"}),
            },
        )
    migrate.upgrade()
    with db.get_engine().connect() as conn:
        data = conn.execute(text("SELECT data FROM settings WHERE \"group\" = 'voicemail'")).scalar_one()
    data = json.loads(data) if isinstance(data, str) else data
    assert data == {"from_name": "VM", "templates": {"fr": {"vm_subject": "Nouveau", "vm_body": "Bonjour"}}}


def test_0007_keeps_callgroup_members(runtime: config.RuntimeConfig) -> None:
    from alembic import command
    from factories import sample_pbx

    migrate.upgrade()
    with db.session_scope() as s:
        sample_pbx(s)
    count = "SELECT COUNT(*) FROM callgroup_members"
    with db.get_engine().connect() as conn:
        total = conn.execute(text(count)).scalar_one()
    command.downgrade(migrate.alembic_config(), "0006")
    with db.get_engine().connect() as conn:
        # the nested group's call group member has no place in the old table
        assert conn.execute(text(count)).scalar_one() == total - 1
    migrate.upgrade()
    with db.get_engine().connect() as conn:
        assert conn.execute(text(count)).scalar_one() == total - 1
        assert compare_metadata(MigrationContext.configure(conn), Base.metadata) == []
