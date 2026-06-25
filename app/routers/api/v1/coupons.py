from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.responses import success
from app.database.connection import get_db
from app.database.models import Coupon, Warehouse
from app.dependencies import admin_required
from app.services.order_service import apply_coupon, transfer_stock

router = APIRouter(tags=["API v1 - Coupons & Warehouses"])


class CouponValidate(BaseModel):
    code: str
    subtotal: float


@router.post("/coupons/validate")
async def validate_coupon(payload: CouponValidate, db: AsyncSession = Depends(get_db)):
    discount, coupon = await apply_coupon(db, payload.code, payload.subtotal, {})
    if not coupon:
        return success({"valid": False, "discount": 0})
    return success({"valid": True, "discount": discount, "code": coupon.code, "type": coupon.discount_type})


@router.get("/coupons")
async def list_coupons(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Coupon).where(Coupon.is_active.is_(True)))
    coupons = result.scalars().all()
    return success([
        {"code": c.code, "type": c.discount_type, "value": c.discount_value, "category": c.category, "expires_at": c.expires_at.isoformat() if c.expires_at else None}
        for c in coupons
    ])


@router.get("/warehouses")
async def list_warehouses(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Warehouse).where(Warehouse.is_active.is_(True)).options(selectinload(Warehouse.stocks))
    )
    warehouses = result.scalars().all()
    data = []
    for wh in warehouses:
        low_stock = [s for s in wh.stocks if 0 < s.quantity < 15]
        data.append({
            "id": wh.id,
            "name": wh.name,
            "location": wh.location,
            "total_skus": len(wh.stocks),
            "low_stock_alerts": len(low_stock),
            "stocks": [{"product_id": s.product_id, "quantity": s.quantity} for s in wh.stocks[:20]],
        })
    return success(data)


class TransferRequest(BaseModel):
    from_warehouse_id: int
    to_warehouse_id: int
    product_id: int
    quantity: int


@router.post("/warehouses/transfer", dependencies=[Depends(admin_required)])
async def api_transfer(payload: TransferRequest, db: AsyncSession = Depends(get_db)):
    try:
        await transfer_stock(db, payload.from_warehouse_id, payload.to_warehouse_id, payload.product_id, payload.quantity)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return success({"message": "Transfer completed"})
