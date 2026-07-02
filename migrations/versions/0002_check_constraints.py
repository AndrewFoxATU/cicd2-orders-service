"""Enforce sale sanity at the database level.

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-02

"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("sales") as batch:
        batch.create_check_constraint("ck_sales_quantity_positive", "quantity > 0")
        batch.create_check_constraint("ck_sales_total_charge_nonnegative", "total_charge >= 0")


def downgrade() -> None:
    with op.batch_alter_table("sales") as batch:
        batch.drop_constraint("ck_sales_quantity_positive", type_="check")
        batch.drop_constraint("ck_sales_total_charge_nonnegative", type_="check")
