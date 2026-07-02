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
from .auth import TokenUser, require_roles, service_auth_headers

TYRES_SERVICE_URL = os.getenv("TYRES_SERVICE_URL", "http://tyres_service:8000")
USERS_SERVICE_URL = os.getenv("USERS_SERVICE_URL", "http://users_service:8000")

app = FastAPI()
Base.metadata.create_all(bind=engine)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/api/sell", response_model=SellRead)
async def sell(
    payload: SellCreate,
    db: Session = Depends(get_db),
    current: TokenUser = Depends(require_roles("admin", "employee+", "employee")),
):
    if payload.quantity <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be > 0")

    # Staff can only record sales as themselves; admins may sell on behalf of others
    if current.role != "admin" and payload.seller_user_id != current.id:
        raise HTTPException(status_code=403, detail="Cannot sell as another user")

    headers = service_auth_headers()
    async with httpx.AsyncClient(timeout=8.0) as client:
        # -----------------------
        # get seller info
        # -----------------------
        u = await client.get(
            f"{USERS_SERVICE_URL}/api/users/{payload.seller_user_id}",
            headers=headers,
        )
        if u.status_code == 404:
            raise HTTPException(status_code=404, detail="Seller not found")
        if u.status_code >= 400:
            raise HTTPException(status_code=502, detail="Users service error")
        seller_name = u.json().get("name")

        # -----------------------
        # reserve stock atomically: the tyres service checks and
        # decrements in a single statement, so two simultaneous
        # sales can never both take the last tyres
        # -----------------------
        d = await client.post(
            f"{TYRES_SERVICE_URL}/api/tyres/{payload.tyre_id}/stock",
            json={"delta": -payload.quantity},
            headers=headers,
        )
        if d.status_code == 404:
            raise HTTPException(status_code=404, detail="Tyre not found")
        if d.status_code == 409:
            raise HTTPException(status_code=409, detail="Not enough stock")
        if d.status_code >= 400:
            raise HTTPException(status_code=502, detail="Failed to update stock")

        tyre = d.json()
        unit_price = Decimal(str(tyre["retail_cost"]))
        total_charge = (unit_price * payload.quantity).quantize(Decimal("0.01"))

    # -----------------------
    # store sale record; if that fails, put the stock back
    # -----------------------
    sale = Sale(
        seller_user_id=payload.seller_user_id,
        tyre_id=payload.tyre_id,
        quantity=payload.quantity,
        total_charge=total_charge,
    )
    try:
        db.add(sale)
        db.commit()
    except Exception:
        db.rollback()
        await _restore_stock(payload.tyre_id, payload.quantity)
        raise HTTPException(
            status_code=502, detail="Failed to record sale; stock restored"
        )
    db.refresh(sale)

    # -----------------------
    # notify (best effort — a broker outage must not undo a stored sale)
    # -----------------------
    try:
        await publish_message("sale.created", {
            "sale_id": sale.id,
            "seller_user_id": payload.seller_user_id,
            "seller_name": seller_name,
            "tyre_id": payload.tyre_id,
            "quantity": payload.quantity,
            "total_charge": str(total_charge),
        })
    except Exception as exc:
        print(f"[sell] sale {sale.id} stored but event publish failed: {exc}")

    result = SellRead.model_validate(sale)
    result.seller_name = seller_name
    return result


async def _restore_stock(tyre_id: int, quantity: int) -> None:
    """Compensate a failed sale by adding the reserved stock back."""
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.post(
                f"{TYRES_SERVICE_URL}/api/tyres/{tyre_id}/stock",
                json={"delta": quantity},
                headers=service_auth_headers(),
            )
        if r.status_code >= 400:
            print(f"[sell] MANUAL FIX NEEDED: could not restore {quantity} stock for tyre {tyre_id} (HTTP {r.status_code})")
    except Exception as exc:
        print(f"[sell] MANUAL FIX NEEDED: could not restore {quantity} stock for tyre {tyre_id}: {exc}")
