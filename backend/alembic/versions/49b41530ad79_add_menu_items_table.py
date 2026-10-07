"""add_menu_items_table

Revision ID: 49b41530ad79
Revises: bfbb7241997b
Create Date: 2026-10-07 11:05:04.062268

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '49b41530ad79'
down_revision: Union[str, None] = 'bfbb7241997b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "menu_items",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("place_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("price_ils", sa.Integer(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("source", sa.String(30), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["place_id"], ["places.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_menu_items_place_id", "menu_items", ["place_id"])
    op.create_index("ix_menu_items_place_name", "menu_items", ["place_id", "name"])


def downgrade() -> None:
    op.drop_table("menu_items")
