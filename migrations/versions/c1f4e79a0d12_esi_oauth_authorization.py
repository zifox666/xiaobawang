"""esi_oauth_authorization

迁移 ID: c1f4e79a0d12
父迁移: bfad6ec1b72d
创建时间: 2026-02-23 00:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "c1f4e79a0d12"
down_revision: str | Sequence[str] | None = "bfad6ec1b72d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade(name: str = "") -> None:
    if name:
        return
    op.create_table(
        "esi_oauth_authorization",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("character_id", sa.Integer(), nullable=False),
        sa.Column("character_name", sa.String(), nullable=False),
        sa.Column("owner_hash", sa.String(), nullable=False),
        sa.Column("refresh_token", sa.Text(), nullable=False),
        sa.Column("scopes", sa.Text(), nullable=False),
        sa.Column("last_authorized_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_esi_oauth_authorization")),
        sa.UniqueConstraint("character_id", name=op.f("uq_esi_oauth_authorization_character_id")),
    )
    op.create_index(
        op.f("ix_esi_oauth_authorization_character_id"),
        "esi_oauth_authorization",
        ["character_id"],
        unique=True,
    )


def downgrade(name: str = "") -> None:
    if name:
        return
    op.drop_index(op.f("ix_esi_oauth_authorization_character_id"), table_name="esi_oauth_authorization")
    op.drop_table("esi_oauth_authorization")
