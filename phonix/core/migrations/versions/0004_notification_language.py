# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
"""e-mail notification language per phone, voicemail e-mail texts per language

Revision ID: 0004
Revises: 0001
Create Date: 2026-10-14 20:00:00.000000

(0002 and 0003 were pre-1.0 nightly revisions, see ``migrate.SQUASHED_REVISIONS``.)
"""

from __future__ import annotations

import json
from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("phones") as batch:
        batch.add_column(sa.Column("notify_language", sa.String(length=16), nullable=False, server_default=""))
    with op.batch_alter_table("phones") as batch:
        batch.alter_column("notify_language", server_default=None)

    # the single custom voicemail e-mail subject/body applied to every mailbox: keep it for
    # the default prompt language, the language it was most likely written in
    conn = op.get_bind()
    rows: dict[str, Any] = {row[0]: row[1] for row in conn.execute(sa.text('SELECT "group", data FROM settings'))}
    raw = rows.get("voicemail")
    if raw is None:
        return
    data = json.loads(raw) if isinstance(raw, str) else dict(raw)
    subject = data.pop("custom_subject", "") or ""
    body = data.pop("custom_body", "") or ""
    if subject or body:
        system = rows.get("system")
        system_data = (json.loads(system) if isinstance(system, str) else system) or {}
        lang = system_data.get("prompt_language") or "en"
        data.setdefault("templates", {})[lang] = {"vm_subject": subject, "vm_body": body}
    conn.execute(sa.text("UPDATE settings SET data = :data WHERE \"group\" = 'voicemail'"), {"data": json.dumps(data)})


def downgrade() -> None:
    with op.batch_alter_table("phones") as batch:
        batch.drop_column("notify_language")
