# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
"""call groups as call group members

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-22 12:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def _members_table(name: str, nested: bool) -> None:
    columns: list[sa.Column[int]] = [
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("phone_id", sa.Integer(), nullable=nested),
    ]
    constraints: list[sa.Constraint] = [
        sa.ForeignKeyConstraint(["group_id"], ["callgroups.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["phone_id"], ["phones.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("group_id", "phone_id"),
    ]
    if nested:
        columns.append(sa.Column("member_group_id", sa.Integer(), nullable=True))
        constraints += [
            sa.ForeignKeyConstraint(["member_group_id"], ["callgroups.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("group_id", "member_group_id"),
            sa.CheckConstraint("(phone_id IS NULL) != (member_group_id IS NULL)", name="ck_callgroup_member_kind"),
        ]
    op.create_table(name, *columns, sa.Column("position", sa.Integer(), nullable=False), *constraints)


# SQLite cannot alter columns or add foreign keys: rebuild the table
def upgrade() -> None:
    _members_table("callgroup_members_new", nested=True)
    op.execute(
        "INSERT INTO callgroup_members_new (id, group_id, phone_id, position) "
        "SELECT id, group_id, phone_id, position FROM callgroup_members"
    )
    op.drop_table("callgroup_members")
    op.rename_table("callgroup_members_new", "callgroup_members")


def downgrade() -> None:
    _members_table("callgroup_members_old", nested=False)
    op.execute(
        "INSERT INTO callgroup_members_old (id, group_id, phone_id, position) "
        "SELECT id, group_id, phone_id, position FROM callgroup_members WHERE phone_id IS NOT NULL"
    )
    op.drop_table("callgroup_members")
    op.rename_table("callgroup_members_old", "callgroup_members")
