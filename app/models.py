# orders_service/models.py
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import CheckConstraint, Integer, Numeric
from decimal import Decimal

class Base(DeclarativeBase):
    pass

class Sale(Base):
    __tablename__ = "sales"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_sales_quantity_positive"),
        CheckConstraint("total_charge >= 0", name="ck_sales_total_charge_nonnegative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    seller_user_id: Mapped[int] = mapped_column(Integer, nullable=False)

    tyre_id: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    # how much to charge the customer for this sale
    total_charge: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=0)
