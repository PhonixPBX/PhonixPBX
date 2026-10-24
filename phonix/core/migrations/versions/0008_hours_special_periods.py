# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
"""special periods of business hours

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-24 12:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "business_hours_specials",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("hours_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("start", sa.Date(), nullable=True),
        sa.Column("end", sa.Date(), nullable=True),
        sa.Column("yearly", sa.Boolean(), nullable=False),
        sa.Column("feature_code", sa.String(length=16), nullable=True),
        sa.Column("dest_type", sa.String(length=16), nullable=False),
        sa.Column("dest_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["hours_id"], ["business_hours.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("feature_code"),
    )


def downgrade() -> None:
    op.drop_table("business_hours_specials")
