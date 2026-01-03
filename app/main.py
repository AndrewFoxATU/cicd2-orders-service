# orders_service/main.py
import os
from decimal import Decimal

import httpx
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session

from .database import engine, get_db
from .models import Base, Sale
from .schemas import SellCreate, SellRead
from .main_topic import publish_message

TYRES_SERVICE_URL = os.getenv("TYRES_SERVICE_URL", "http://tyres_service:8000")
USERS_SERVICE_URL = os.getenv("USERS_SERVICE_URL", "http://users_service:8000")

app = FastAPI()
Base.metadata.create_all(bind=engine)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/sell", response_model=SellRead)
async def sell(payload: SellCreate, db: Session = Depends(get_db)):
    if payload.quantity <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be > 0")

    async with httpx.AsyncClient(timeout=8.0) as client:
        # -----------------------
        # get seller info
        # -----------------------
        u = await client.get(f"{USERS_SERVICE_URL}/api/users/{payload.seller_user_id}")
        if u.status_code == 404:
            raise HTTPException(status_code=404, detail="Seller not found")
        if u.status_code >= 400:
            raise HTTPException(status_code=502, detail="Users service error")
        seller_name = u.json().get("name")

        # -----------------------
        # get tyre + check stock
        # -----------------------
        t = await client.get(f"{TYRES_SERVICE_URL}/api/tyres/{payload.tyre_id}")
        if t.status_code == 404:
            raise HTTPException(status_code=404, detail="Tyre not found")
        if t.status_code >= 400:
            raise HTTPException(status_code=502, detail="Tyres service error")

        tyre = t.json()
        current_qty = int(tyre["quantity"])

        if current_qty < payload.quantity:
            raise HTTPException(status_code=409, detail="Not enough stock")

        unit_price = Decimal(str(tyre["retail_cost"]))
        total_charge = (unit_price * payload.quantity).quantize(Decimal("0.01"))

        # -----------------------
        # update quantity (sell)
        # -----------------------
        new_qty = current_qty - payload.quantity
        p = await client.patch(
            f"{TYRES_SERVICE_URL}/api/tyres/{payload.tyre_id}",
            json={"quantity": new_qty},
        )
        if p.status_code >= 400:
            raise HTTPException(status_code=502, detail="Failed to update stock")

    # -----------------------
    # store sale record
    # -----------------------
    sale = Sale(
        seller_user_id=payload.seller_user_id,
        tyre_id=payload.tyre_id,
        quantity=payload.quantity,
        total_charge=total_charge,
    )
    db.add(sale)
    db.commit()
    db.refresh(sale)

    await publish_message("sale.created", {
        "sale_id": sale.id,
        "seller_user_id": payload.seller_user_id,
        "seller_name": seller_name,
        "tyre_id": payload.tyre_id,
        "quantity": payload.quantity,
        "total_charge": str(total_charge),
    })

    result = SellRead.model_validate(sale)
    result.seller_name = seller_name
    return result
