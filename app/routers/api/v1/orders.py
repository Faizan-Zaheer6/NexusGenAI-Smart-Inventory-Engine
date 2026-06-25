from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.responses import success
from app.database.connection import get_db
from app.database.models import Order, OrderItem, User
from app.dependencies import admin_required, get_current_user
from app.services.order_service import advance_order_status, create_order_from_cart

router = APIRouter(prefix="/orders", tags=["API v1 - Orders"])


class CheckoutRequest(BaseModel):
    coupon_code: str | None = None
    warehouse_id: int | None = None


@router.post("/checkout")
async def api_checkout(payload: CheckoutRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    order = await create_order_from_cart(db, user.id, payload.coupon_code, payload.warehouse_id)
    if not order:
        raise HTTPException(status_code=400, detail="Cart is empty")
    return success({"order_id": order.id, "total": order.total_amount, "status": order.status})


@router.get("/mine")
async def api_my_orders(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    result = await db.execute(select(Order).where(Order.user_id == user.id).order_by(Order.created_at.desc()))
    orders = result.scalars().all()
    return success([
        {"id": o.id, "total": o.total_amount, "status": o.status, "discount": o.discount_amount, "created_at": o.created_at.isoformat()}
        for o in orders
    ])


@router.get("/{order_id}")
async def api_order_detail(order_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    result = await db.execute(
        select(Order)
        .where(Order.id == order_id, Order.user_id == user.id)
        .options(selectinload(Order.items).selectinload(OrderItem.product))
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return success({
        "id": order.id,
        "status": order.status,
        "subtotal": order.subtotal,
        "discount": order.discount_amount,
        "total": order.total_amount,
        "coupon": order.coupon_code,
        "created_at": order.created_at.isoformat(),
        "items": [
            {"product": item.product.name, "quantity": item.quantity, "unit_price": item.unit_price, "line_total": item.quantity * item.unit_price}
            for item in order.items
        ],
    })


class StatusUpdate(BaseModel):
    status: str
    note: str | None = None


@router.get("")
async def api_admin_orders(
    status: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(admin_required),
):
    query = select(Order).options(selectinload(Order.user)).order_by(Order.created_at.desc())
    if status:
        query = query.where(Order.status == status)
    result = await db.execute(query)
    orders = result.scalars().all()
    return success([
        {"id": o.id, "customer": o.user.full_name, "total": o.total_amount, "status": o.status, "created_at": o.created_at.isoformat()}
        for o in orders
    ])


@router.patch("/{order_id}/status")
async def api_update_status(
    order_id: int,
    payload: StatusUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(admin_required),
):
    try:
        order = await advance_order_status(db, order_id, payload.status, admin.id, payload.note)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return success({"id": order.id, "status": order.status})
