# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
"""IVR menus and business hours

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-17 12:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ivr_menus",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("extension", sa.String(length=32), nullable=True),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("public_access", sa.Boolean(), nullable=False),
        sa.Column("public_name", sa.String(length=64), nullable=False),
        sa.Column("prompt_mode", sa.String(length=16), nullable=False),
        sa.Column("prompt_media_id", sa.Integer(), nullable=True),
        sa.Column("prompt_sound", sa.String(length=64), nullable=False),
        sa.Column("prompt_text", sa.Text(), nullable=False),
        sa.Column("timeout", sa.Integer(), nullable=False),
        sa.Column("repeats", sa.Integer(), nullable=False),
        sa.Column("direct_dial", sa.Boolean(), nullable=False),
        sa.Column("timeout_dest_type", sa.String(length=16), nullable=False),
        sa.Column("timeout_dest_id", sa.Integer(), nullable=True),
        sa.Column("invalid_dest_type", sa.String(length=16), nullable=False),
        sa.Column("invalid_dest_id", sa.Integer(), nullable=True),
        sa.Column("legacy_uniqid", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["prompt_media_id"], ["media_files.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("extension"),
    )
    op.create_table(
        "ivr_options",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("menu_id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=1), nullable=False),
        sa.Column("label", sa.String(length=80), nullable=False),
        sa.Column("dest_type", sa.String(length=16), nullable=False),
        sa.Column("dest_id", sa.Integer(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["menu_id"], ["ivr_menus.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("menu_id", "key"),
    )
    op.create_table(
        "business_hours",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("feature_code", sa.String(length=16), nullable=True),
        sa.Column("open_dest_type", sa.String(length=16), nullable=False),
        sa.Column("open_dest_id", sa.Integer(), nullable=True),
        sa.Column("closed_dest_type", sa.String(length=16), nullable=False),
        sa.Column("closed_dest_id", sa.Integer(), nullable=True),
        sa.Column("legacy_uniqid", sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("feature_code"),
    )
    op.create_table(
        "business_hours_ranges",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("hours_id", sa.Integer(), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("start", sa.String(length=5), nullable=False),
        sa.Column("end", sa.String(length=5), nullable=False),
        sa.ForeignKeyConstraint(["hours_id"], ["business_hours.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "business_hours_holidays",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("hours_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("yearly", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["hours_id"], ["business_hours.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("business_hours_holidays")
    op.drop_table("business_hours_ranges")
    op.drop_table("business_hours")
    op.drop_table("ivr_options")
    op.drop_table("ivr_menus")
