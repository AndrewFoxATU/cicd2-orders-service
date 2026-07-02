"""Initial sales schema.

Matches the schema existing deployments already have (created by
Base.metadata.create_all), so existing databases are stamped at this
revision instead of running it.

Revision ID: 0001
Revises:
Create Date: 2026-07-02

"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sales",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("seller_user_id", sa.Integer(), nullable=False),
        sa.Column("tyre_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("total_charge", sa.Numeric(10, 2), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("sales")
