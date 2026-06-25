from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.audit import log_audit
from app.core.config import get_settings
from app.database.models import (
    ORDER_STATUSES,
    CartItem,
    Coupon,
    FlashSale,
    Order,
    OrderItem,
    OrderStatusHistory,
    Product,
    Warehouse,
    WarehouseStock,
)

settings = get_settings()
STATUS_FLOW = ["Pending", "Processing", "Shipped", "Delivered"]


async def get_active_flash_sale(db: AsyncSession, product_id: int) -> Optional[FlashSale]:
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(FlashSale).where(
            FlashSale.product_id == product_id,
            FlashSale.is_active.is_(True),
            FlashSale.ends_at > now,
        )
    )
    return result.scalar_one_or_none()


def effective_price(product: Product, flash_sale: Optional[FlashSale] = None) -> float:
    if flash_sale:
        return round(product.price * (1 - flash_sale.discount_percent / 100), 2)
    return product.price


async def apply_coupon(db: AsyncSession, code: str, subtotal: float, category_amounts: dict) -> tuple[float, Optional[Coupon]]:
    result = await db.execute(select(Coupon).where(Coupon.code == code.upper(), Coupon.is_active.is_(True)))
    coupon = result.scalar_one_or_none()
    if not coupon:
        return 0.0, None
    now = datetime.now(timezone.utc)
    if coupon.expires_at and coupon.expires_at < now:
        return 0.0, None
    if coupon.max_uses and coupon.used_count >= coupon.max_uses:
        return 0.0, None
    base = subtotal
    if coupon.category and coupon.category in category_amounts:
        base = category_amounts[coupon.category]
    if base < coupon.min_order_amount:
        return 0.0, None
    if coupon.discount_type == "percent":
        discount = round(base * (coupon.discount_value / 100), 2)
    else:
        discount = round(min(coupon.discount_value, base), 2)
    return discount, coupon


async def create_order_from_cart(
    db: AsyncSession,
    user_id: int,
    coupon_code: Optional[str] = None,
    warehouse_id: Optional[int] = None,
) -> Optional[Order]:
    cart_res = await db.execute(
        select(CartItem).where(CartItem.user_id == user_id).options(selectinload(CartItem.product))
    )
    cart_items = cart_res.scalars().all()
    if not cart_items:
        return None

    subtotal = 0.0
    category_amounts: dict[str, float] = {}
    line_prices: list[tuple[CartItem, float]] = []

    for item in cart_items:
        flash = await get_active_flash_sale(db, item.product_id)
        price = effective_price(item.product, flash)
        line_total = price * item.quantity
        subtotal += line_total
        category_amounts[item.product.category] = category_amounts.get(item.product.category, 0) + line_total
        line_prices.append((item, price))

    discount_amount = 0.0
    coupon = None
    if coupon_code:
        discount_amount, coupon = await apply_coupon(db, coupon_code, subtotal, category_amounts)

    total = max(0.0, round(subtotal - discount_amount, 2))
    order = Order(
        user_id=user_id,
        subtotal=round(subtotal, 2),
        discount_amount=discount_amount,
        total_amount=total,
        status="Pending",
        coupon_code=coupon.code if coupon else None,
        warehouse_id=warehouse_id,
    )
    db.add(order)
    await db.flush()
    db.add(OrderStatusHistory(order_id=order.id, old_status="", new_status="Pending", note="Order placed"))

    for item, price in line_prices:
        db.add(OrderItem(order_id=order.id, product_id=item.product_id, quantity=item.quantity, unit_price=price))
        item.product.stock = max(0, item.product.stock - item.quantity)
        if warehouse_id:
            ws_res = await db.execute(
                select(WarehouseStock).where(
                    WarehouseStock.warehouse_id == warehouse_id,
                    WarehouseStock.product_id == item.product_id,
                )
            )
            ws = ws_res.scalar_one_or_none()
            if ws:
                ws.quantity = max(0, ws.quantity - item.quantity)
        await db.delete(item)

    if coupon:
        coupon.used_count += 1

    await db.commit()
    await db.refresh(order)

    try:
        from app.services.email_service import send_order_confirmation, send_low_stock_alert
        from app.core.background import run_background
        from app.core.logger import logger

        order_res = await db.execute(
            select(Order)
            .where(Order.id == order.id)
            .options(selectinload(Order.items).selectinload(OrderItem.product), selectinload(Order.user))
        )
        loaded_order = order_res.scalar_one()

        run_background(send_order_confirmation(loaded_order.user.email, loaded_order))

        for item in loaded_order.items:
            if item.product.stock < settings.LOW_STOCK_THRESHOLD:
                run_background(send_low_stock_alert([settings.ADMIN_EMAIL], item.product))
    except Exception as exc:
        logger.error("Failed to trigger order emails: %s", exc)

    return order


async def advance_order_status(
    db: AsyncSession,
    order_id: int,
    new_status: str,
    changed_by: Optional[int] = None,
    note: Optional[str] = None,
) -> Order:
    result = await db.execute(select(Order).where(Order.id == order_id).options(selectinload(Order.items)))
    order = result.scalar_one_or_none()
    if not order:
        raise ValueError("Order not found")
    if new_status not in ORDER_STATUSES:
        raise ValueError("Invalid status")
    old = order.status
    if old == new_status:
        return order
    if new_status in STATUS_FLOW and old in STATUS_FLOW:
        if STATUS_FLOW.index(new_status) < STATUS_FLOW.index(old):
            raise ValueError("Cannot move status backwards")
    order.status = new_status
    db.add(OrderStatusHistory(order_id=order.id, old_status=old, new_status=new_status, changed_by=changed_by, note=note))
    await db.commit()
    await db.refresh(order)
    return order


async def get_frequently_bought_together(db: AsyncSession, product_id: int, limit: int = 4) -> list[Product]:
    subq = (
        select(OrderItem.order_id)
        .where(OrderItem.product_id == product_id)
        .scalar_subquery()
    )
    result = await db.execute(
        select(Product, func.sum(OrderItem.quantity).label("freq"))
        .join(OrderItem, OrderItem.product_id == Product.id)
        .where(OrderItem.order_id.in_(subq), Product.id != product_id)
        .group_by(Product.id)
        .order_by(func.sum(OrderItem.quantity).desc())
        .limit(limit)
    )
    return [row[0] for row in result.all()]


async def sync_product_stock_from_warehouses(db: AsyncSession, product_id: int) -> None:
    result = await db.execute(
        select(func.coalesce(func.sum(WarehouseStock.quantity), 0))
        .select_from(WarehouseStock)
        .where(WarehouseStock.product_id == product_id)
    )
    total = result.scalar() or 0
    prod_res = await db.execute(select(Product).where(Product.id == product_id))
    product = prod_res.scalar_one_or_none()
    if product:
        product.stock = int(total)
        await db.commit()


async def transfer_stock(
    db: AsyncSession,
    from_id: int,
    to_id: int,
    product_id: int,
    quantity: int,
    user_id: Optional[int] = None,
) -> None:
    from app.database.models import StockTransfer

    if from_id == to_id or quantity <= 0:
        raise ValueError("Invalid transfer")
    src_res = await db.execute(
        select(WarehouseStock).where(WarehouseStock.warehouse_id == from_id, WarehouseStock.product_id == product_id)
    )
    src = src_res.scalar_one_or_none()
    if not src or src.quantity < quantity:
        raise ValueError("Insufficient stock at source warehouse")
    dst_res = await db.execute(
        select(WarehouseStock).where(WarehouseStock.warehouse_id == to_id, WarehouseStock.product_id == product_id)
    )
    dst = dst_res.scalar_one_or_none()
    if not dst:
        dst = WarehouseStock(warehouse_id=to_id, product_id=product_id, quantity=0)
        db.add(dst)
    src.quantity -= quantity
    dst.quantity += quantity
    db.add(StockTransfer(from_warehouse_id=from_id, to_warehouse_id=to_id, product_id=product_id, quantity=quantity, transferred_by=user_id))
    await sync_product_stock_from_warehouses(db, product_id)
    await log_audit(db, "stock_transfer", "warehouse", product_id, f"{quantity} units from WH{from_id} to WH{to_id}", user_id)
    await db.commit()
