# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
"""API tokens that may place calls

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-16 12:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("api_tokens") as batch:
        batch.add_column(sa.Column("allow_calls", sa.Boolean(), nullable=False, server_default=sa.false()))
    with op.batch_alter_table("api_tokens") as batch:
        batch.alter_column("allow_calls", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("api_tokens") as batch:
        batch.drop_column("allow_calls")
