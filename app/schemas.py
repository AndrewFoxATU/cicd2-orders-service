# orders_service/schemas.py
from pydantic import BaseModel
from decimal import Decimal

class SellCreate(BaseModel):
    seller_user_id: int
    tyre_id: int
    quantity: int

class SellRead(BaseModel):
    id: int
    seller_user_id: int
    seller_name: str | None = None

    tyre_id: int
    quantity: int
    total_charge: Decimal

    class Config:
        from_attributes = True
