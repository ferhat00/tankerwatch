"""Initial schema

Revision ID: 0001
Revises:
Create Date: 2024-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "vessels",
        sa.Column("imo", sa.String(), nullable=False),
        sa.Column("mmsi", sa.String(), nullable=True),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("vessel_type", sa.String(), nullable=True),
        sa.Column("vessel_type_raw", sa.String(), nullable=True),
        sa.Column("dwt", sa.Integer(), nullable=True),
        sa.Column("built_year", sa.Integer(), nullable=True),
        sa.Column("flag", sa.String(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("imo"),
    )

    op.create_table(
        "ports",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("unlocode", sa.String(), nullable=True),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lon", sa.Float(), nullable=False),
        sa.Column("port_type", sa.String(), nullable=True),
        sa.Column("country", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "positions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("imo", sa.String(), nullable=False),
        sa.Column("scraped_at", sa.DateTime(), nullable=False),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lon", sa.Float(), nullable=True),
        sa.Column("speed", sa.Float(), nullable=True),
        sa.Column("heading", sa.Integer(), nullable=True),
        sa.Column("nav_status", sa.String(), nullable=True),
        sa.Column("destination", sa.String(), nullable=True),
        sa.Column("eta", sa.DateTime(), nullable=True),
        sa.Column("draught", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["imo"], ["vessels.imo"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "port_visits",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("imo", sa.String(), nullable=False),
        sa.Column("port_id", sa.Integer(), nullable=True),
        sa.Column("port_name", sa.String(), nullable=True),
        sa.Column("port_unlocode", sa.String(), nullable=True),
        sa.Column("arrived_at", sa.DateTime(), nullable=False),
        sa.Column("departed_at", sa.DateTime(), nullable=True),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lon", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["imo"], ["vessels.imo"]),
        sa.ForeignKeyConstraint(["port_id"], ["ports.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("port_visits")
    op.drop_table("positions")
    op.drop_table("ports")
    op.drop_table("vessels")
