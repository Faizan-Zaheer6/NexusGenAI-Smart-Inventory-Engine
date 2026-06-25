from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.audit import log_audit
from app.core.config import get_settings
from app.core.logger import logger
from app.database.connection import get_db
from app.database.models import AuditLog, CartItem, Coupon, Order, Product, User, Warehouse, WarehouseStock
from app.dependencies import admin_required, super_admin_required, get_current_user
from app.services.order_service import advance_order_status, transfer_stock
from app.services.product_service import invalidate_product_cache
from app.services.report_service import generate_sales_excel, generate_sales_pdf

router = APIRouter(prefix="/admin", tags=["Admin"])
settings = get_settings()
TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)


@router.get("", dependencies=[Depends(admin_required)])
async def admin_dashboard(
    request: Request,
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from collections import defaultdict
    from app.database.models import OrderItem

    products_res = await db.execute(select(Product).order_by(Product.id))
    products = products_res.scalars().all()
    low_stock_count = sum(1 for p in products if 0 < p.stock < settings.LOW_STOCK_THRESHOLD)
    out_of_stock_count = sum(1 for p in products if p.stock == 0)
    total_stock_units = sum(p.stock for p in products)

    order_query = select(func.sum(Order.total_amount))
    df, dt = _parse_date(date_from), _parse_date(date_to)
    if df:
        order_query = order_query.where(Order.created_at >= df)
    if dt:
        order_query = order_query.where(Order.created_at <= dt + timedelta(days=1))
    sales_res = await db.execute(order_query)
    total_sales_sum = sales_res.scalar() or 0.0

    user_count = (await db.execute(select(func.count(User.id)))).scalar() or 0
    active_carts = (await db.execute(select(func.count(func.distinct(CartItem.user_id))))).scalar() or 0

    audit_res = await db.execute(
        select(AuditLog).options(selectinload(AuditLog.user)).order_by(AuditLog.created_at.desc()).limit(15)
    )
    audit_logs = audit_res.scalars().all()

    wh_res = await db.execute(select(Warehouse).options(selectinload(Warehouse.stocks)))
    warehouses = wh_res.scalars().all()
    warehouse_alerts = []
    for wh in warehouses:
        low = [s for s in wh.stocks if 0 < s.quantity < settings.LOW_STOCK_THRESHOLD]
        if low:
            warehouse_alerts.append({"warehouse": wh.name, "count": len(low)})

    coupon_res = await db.execute(select(Coupon).where(Coupon.is_active.is_(True)))
    coupons = coupon_res.scalars().all()

    # Calculate 30-day Sales Trend (daily sum of Order.total_amount)
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    trend_q = select(Order.created_at, Order.total_amount).where(Order.created_at >= thirty_days_ago)
    trend_res = await db.execute(trend_q)
    daily_sums = defaultdict(float)
    for created_at, total_amount in trend_res.all():
        day_str = created_at.strftime("%Y-%m-%d")
        daily_sums[day_str] += total_amount
    sorted_days = sorted(daily_sums.keys())
    sales_trend_labels = sorted_days
    sales_trend_data = [round(daily_sums[d], 2) for d in sorted_days]

    # Calculate Revenue by Category
    cat_revenue_q = (
        select(Product.category, func.sum(OrderItem.quantity * OrderItem.unit_price))
        .join(OrderItem, OrderItem.product_id == Product.id)
        .group_by(Product.category)
    )
    cat_res = await db.execute(cat_revenue_q)
    category_revenue_labels = []
    category_revenue_data = []
    for row in cat_res.all():
        category_revenue_labels.append(row[0])
        category_revenue_data.append(round(row[1], 2))

    # Calculate Top Selling Products
    top_products_q = (
        select(Product.id, Product.name, Product.category, func.sum(OrderItem.quantity).label("sold"), func.sum(OrderItem.quantity * OrderItem.unit_price).label("revenue"))
        .join(OrderItem, OrderItem.product_id == Product.id)
        .group_by(Product.id, Product.name, Product.category)
        .order_by(func.sum(OrderItem.quantity).desc())
        .limit(5)
    )
    top_res = await db.execute(top_products_q)
    top_selling_products = [
        {"id": row[0], "name": row[1], "category": row[2], "sold": int(row[3]), "revenue": round(row[4], 2)}
        for row in top_res.all()
    ]

    # Calculate Restock Recommendations
    restock_products = []
    for p in products:
        if p.stock < settings.LOW_STOCK_THRESHOLD:
            restock_products.append({
                "id": p.id,
                "name": p.name,
                "category": p.category,
                "stock": p.stock,
                "recommended": 50 - p.stock
            })
    restock_products = sorted(restock_products, key=lambda x: x["stock"])[:5]

    return templates.TemplateResponse(
        request=request,
        name="admin/dashboard.html",
        context={
            "products": products,
            "sales_total": f"${total_sales_sum:,.2f}",
            "low_stock_count": low_stock_count,
            "out_of_stock_count": out_of_stock_count,
            "total_stock_units": total_stock_units,
            "user_count": user_count,
            "active_carts": active_carts,
            "current_user": current_user,
            "low_stock_threshold": settings.LOW_STOCK_THRESHOLD,
            "audit_logs": audit_logs,
            "warehouses": warehouses,
            "warehouse_alerts": warehouse_alerts,
            "coupons": coupons,
            "date_from": date_from or "",
            "date_to": date_to or "",
            "sales_trend_labels": sales_trend_labels,
            "sales_trend_data": sales_trend_data,
            "category_revenue_labels": category_revenue_labels,
            "category_revenue_data": category_revenue_data,
            "top_selling_products": top_selling_products,
            "restock_products": restock_products,
        },
    )


@router.get("/orders", dependencies=[Depends(admin_required)])
async def admin_orders(
    request: Request,
    status_filter: str | None = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(Order).options(selectinload(Order.user), selectinload(Order.items)).order_by(Order.created_at.desc())
    if status_filter:
        query = query.where(Order.status == status_filter)
    orders = (await db.execute(query)).scalars().all()
    return templates.TemplateResponse(
        request=request,
        name="admin/orders.html",
        context={"orders": orders, "current_user": current_user, "status_filter": status_filter or "all"},
    )


@router.get("/orders/{order_id}", dependencies=[Depends(admin_required)])
async def admin_order_detail(
    order_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.database.models import OrderItem

    result = await db.execute(
        select(Order)
        .where(Order.id == order_id)
        .options(selectinload(Order.user), selectinload(Order.items).selectinload(OrderItem.product), selectinload(Order.status_history))
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return templates.TemplateResponse(
        request=request,
        name="admin/order_detail.html",
        context={"order": order, "current_user": current_user, "statuses": ["Pending", "Processing", "Shipped", "Delivered", "Cancelled"]},
    )


@router.post("/orders/{order_id}/status", dependencies=[Depends(admin_required)])
async def admin_update_order_status(
    order_id: int,
    new_status: str = Form(...),
    note: str = Form(""),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_user),
):
    try:
        await advance_order_status(db, order_id, new_status, admin.id, note or None)
        await log_audit(db, f"order_status_{new_status.lower()}", "order", order_id, note, admin.id)
        await db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return RedirectResponse(url=f"/admin/orders/{order_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/product", dependencies=[Depends(super_admin_required)])
async def create_product(
    request: Request,
    name: str = Form(...),
    price: float = Form(...),
    stock: int = Form(...),
    category: str = Form(...),
    image_url: str = Form(""),
    description: str = Form(""),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_user),
):
    product = Product(
        name=name, price=price, stock=stock, category=category,
        image_url=image_url or "https://images.unsplash.com/photo-1542751371-adc38448a05e?w=400",
        description=description,
    )
    db.add(product)
    await db.flush()
    await log_audit(db, "product_create", "product", product.id, name, admin.id, request.client.host if request.client else None)
    await db.commit()
    await invalidate_product_cache()
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/product/{product_id}/edit", dependencies=[Depends(super_admin_required)])
async def edit_product(
    product_id: int,
    request: Request,
    name: str = Form(...),
    price: float = Form(...),
    stock: int = Form(...),
    category: str = Form(...),
    image_url: str = Form(""),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_user),
):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    product.name, product.price, product.stock, product.category = name, price, stock, category
    if image_url:
        product.image_url = image_url
    await log_audit(db, "product_update", "product", product_id, name, admin.id)
    await db.commit()
    await invalidate_product_cache()
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/product/{product_id}/inline", dependencies=[Depends(admin_required)])
async def inline_edit_product(
    product_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_user),
):
    from fastapi.responses import JSONResponse

    if "application/json" in request.headers.get("content-type", ""):
        body = await request.json()
        field, value = body.get("field"), body.get("value")
    else:
        form = await request.form()
        field, value = form.get("field"), form.get("value")

    if field in ("price", "name", "category") and admin.role != "admin":
        raise HTTPException(status_code=403, detail="Super Admin privileges required to edit core properties")

    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    if field == "price":
        product.price = float(value)
    elif field == "stock":
        product.stock = int(value)
    elif field == "name":
        product.name = str(value)
    elif field == "category":
        product.category = str(value)
    else:
        raise HTTPException(status_code=400, detail="Invalid field")

    await log_audit(db, "product_inline_edit", "product", product_id, f"{field}={value}", admin.id)
    await db.commit()
    await invalidate_product_cache()

    if "application/json" in request.headers.get("content-type", ""):
        return JSONResponse({"success": True, "field": field, "value": value})
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/product/{product_id}/delete", dependencies=[Depends(super_admin_required)])
async def delete_product(product_id: int, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_user)):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    await log_audit(db, "product_delete", "product", product_id, product.name, admin.id)
    await db.delete(product)
    await db.commit()
    await invalidate_product_cache()
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/stock/add/{product_id}", dependencies=[Depends(admin_required)])
async def add_stock(product_id: int, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_user)):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if product:
        product.stock += 1
        await log_audit(db, "stock_increase", "product", product_id, "+1", admin.id)
        await db.commit()
        await invalidate_product_cache()
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/stock/reduce/{product_id}", dependencies=[Depends(admin_required)])
async def reduce_stock(product_id: int, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_user)):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if product and product.stock > 0:
        product.stock -= 1
        await log_audit(db, "stock_decrease", "product", product_id, "-1", admin.id)
        await db.commit()
        await invalidate_product_cache()
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/import/csv", dependencies=[Depends(admin_required)])
async def import_csv(
    request: Request,
    csv_data: str = Form(...),
    background_tasks: BackgroundTasks = None,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_user),
):
    import csv
    import io

    reader = csv.DictReader(io.StringIO(csv_data))
    count = 0
    for row in reader:
        db.add(Product(
            name=row.get("name", "Imported Item"),
            category=row.get("category", "General"),
            price=float(row.get("price", 0)),
            stock=int(row.get("stock", 0)),
            image_url=row.get("image_url", ""),
        ))
        count += 1
    await log_audit(db, "bulk_import", "product", None, f"{count} products imported", admin.id)
    await db.commit()
    if background_tasks:
        from app.core.background import invalidate_cache_async

        async def _clear():
            await invalidate_cache_async("products:*")

        background_tasks.add_task(_clear)
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/export/excel", dependencies=[Depends(admin_required)])
async def export_excel(
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    content = await generate_sales_excel(db, _parse_date(date_from), _parse_date(date_to))
    return StreamingResponse(
        iter([content]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=nexusai_report.xlsx"},
    )


@router.get("/export/pdf", dependencies=[Depends(admin_required)])
async def export_pdf(
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    content = await generate_sales_pdf(db, _parse_date(date_from), _parse_date(date_to))
    return StreamingResponse(
        iter([content]),
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=nexusai_sales_report.pdf"},
    )


@router.post("/warehouse/transfer", dependencies=[Depends(admin_required)])
async def warehouse_transfer(
    from_warehouse_id: int = Form(...),
    to_warehouse_id: int = Form(...),
    product_id: int = Form(...),
    quantity: int = Form(...),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_user),
):
    try:
        await transfer_stock(db, from_warehouse_id, to_warehouse_id, product_id, quantity, admin.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)
