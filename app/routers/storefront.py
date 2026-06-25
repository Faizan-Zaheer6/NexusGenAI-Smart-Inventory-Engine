from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Query, Request, WebSocket, WebSocketDisconnect, status
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.logger import logger
from app.database.connection import get_db
from app.database.models import CartItem, Product, User, WishlistItem
from app.dependencies import get_current_user, get_optional_user
from app.services.order_service import create_order_from_cart
from app.services.product_service import list_products

router = APIRouter(tags=["Storefront"])
settings = get_settings()
TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

active_ws: list[WebSocket] = []


async def _resolve_storefront_user(request: Request, db: AsyncSession) -> Optional[User]:
    user = await get_optional_user(request, db=db)
    if user:
        return user
    result = await db.execute(select(User).where(User.email == settings.GUEST_EMAIL))
    return result.scalar_one_or_none()


async def _load_cart_context(db: AsyncSession, user: Optional[User]) -> dict:
    cart_items, cart_total_items, cart_subtotal = [], 0, 0.0
    if user:
        cart_res = await db.execute(
            select(CartItem).where(CartItem.user_id == user.id).options(selectinload(CartItem.product)).order_by(CartItem.id)
        )
        cart_items = cart_res.scalars().all()
        cart_total_items = sum(i.quantity for i in cart_items)
        cart_subtotal = sum(i.quantity * i.product.price for i in cart_items)
    return {
        "cart_items": cart_items,
        "cart_total_items": cart_total_items,
        "cart_subtotal": f"{cart_subtotal:,.2f}",
        "cart_total": f"{cart_subtotal:,.2f}",
    }


def _cart_json(cart_items: list[CartItem]) -> dict:
    total_items = sum(i.quantity for i in cart_items)
    subtotal = sum(i.quantity * i.product.price for i in cart_items)
    return {
        "items": [{
            "id": i.id, "product_id": i.product_id, "name": i.product.name, "price": i.product.price,
            "quantity": i.quantity, "line_total": round(i.quantity * i.product.price, 2),
            "image_url": i.product.image_url or "https://images.unsplash.com/photo-1542751371-adc38448a05e?w=100",
            "stock": i.product.stock,
        } for i in cart_items],
        "total_items": total_items, "subtotal": round(subtotal, 2), "total": round(subtotal, 2),
    }


async def _broadcast_stock(message: dict) -> None:
    dead = []
    for ws in active_ws:
        try:
            await ws.send_json(message)
        except Exception:
            dead.append(ws)
    for ws in dead:
        active_ws.remove(ws)


@router.websocket("/ws/stock")
async def stock_websocket(websocket: WebSocket):
    await websocket.accept()
    active_ws.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in active_ws:
            active_ws.remove(websocket)


@router.get("/")
async def storefront(
    request: Request,
    page: int = Query(1, ge=1),
    category: str = Query("all"),
    search: str = Query(""),
    sort: str = Query("newest"),
    db: AsyncSession = Depends(get_db),
):
    current_user = await _resolve_storefront_user(request, db)
    products_data, meta = await list_products(db, page, settings.PRODUCTS_PER_PAGE, category if category != "all" else None, search or None, sort)
    cart_context = await _load_cart_context(db, current_user)

    wishlist_ids = []
    if current_user and current_user.email != settings.GUEST_EMAIL:
        wl = await db.execute(select(WishlistItem.product_id).where(WishlistItem.user_id == current_user.id))
        wishlist_ids = [row[0] for row in wl.all()]

    from sqlalchemy import func
    from app.database.models import Product as P
    cats_res = await db.execute(select(P.category, func.count(P.id)).group_by(P.category).order_by(P.category))
    categories = [{"name": r[0], "count": r[1]} for r in cats_res.all()]

    return templates.TemplateResponse(
        request=request,
        name="store/shop.html",
        context={
            "products": products_data,
            "categories": categories,
            "meta": meta,
            "current_user": current_user,
            "is_authenticated": current_user is not None and current_user.email != settings.GUEST_EMAIL,
            "wishlist_ids": wishlist_ids,
            "filters": {"page": page, "category": category, "search": search, "sort": sort},
            **cart_context,
        },
    )


@router.get("/api/cart")
async def get_cart_summary(request: Request, db: AsyncSession = Depends(get_db)):
    user = await _resolve_storefront_user(request, db)
    if not user:
        return JSONResponse(_cart_json([]))
    cart_res = await db.execute(select(CartItem).where(CartItem.user_id == user.id).options(selectinload(CartItem.product)).order_by(CartItem.id))
    return JSONResponse(_cart_json(cart_res.scalars().all()))


@router.post("/cart/add/{product_id}")
async def add_to_cart(product_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    user = await _resolve_storefront_user(request, db)
    if not user:
        raise HTTPException(status_code=404, detail="User session not found")
    product_res = await db.execute(select(Product).where(Product.id == product_id))
    product = product_res.scalar_one_or_none()
    if not product or product.stock <= 0:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JSONResponse({"success": False, "message": "Product unavailable"}, status_code=400)
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    cart_res = await db.execute(select(CartItem).where(CartItem.user_id == user.id, CartItem.product_id == product_id))
    cart_item = cart_res.scalar_one_or_none()
    if cart_item:
        if cart_item.quantity < product.stock:
            cart_item.quantity += 1
    else:
        db.add(CartItem(user_id=user.id, product_id=product_id, quantity=1))
    await db.commit()
    await _broadcast_stock({"type": "stock_update", "product_id": product_id, "stock": product.stock})
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        cart_res = await db.execute(select(CartItem).where(CartItem.user_id == user.id).options(selectinload(CartItem.product)).order_by(CartItem.id))
        return JSONResponse({"success": True, "cart": _cart_json(cart_res.scalars().all())})
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/cart/update/{item_id}")
async def update_cart_item(item_id: int, request: Request, action: str = Form(...), db: AsyncSession = Depends(get_db)):
    user = await _resolve_storefront_user(request, db)
    if not user:
        raise HTTPException(status_code=404, detail="User session not found")
    cart_res = await db.execute(select(CartItem).where(CartItem.id == item_id, CartItem.user_id == user.id).options(selectinload(CartItem.product)))
    cart_item = cart_res.scalar_one_or_none()
    if not cart_item:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JSONResponse({"success": False, "message": "Cart item not found"}, status_code=404)
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    if action == "increase" and cart_item.quantity < cart_item.product.stock:
        cart_item.quantity += 1
        await db.commit()
    elif action == "decrease":
        if cart_item.quantity > 1:
            cart_item.quantity -= 1
            await db.commit()
        else:
            await db.delete(cart_item)
            await db.commit()
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        cart_res = await db.execute(select(CartItem).where(CartItem.user_id == user.id).options(selectinload(CartItem.product)).order_by(CartItem.id))
        return JSONResponse({"success": True, "cart": _cart_json(cart_res.scalars().all())})
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/wishlist/toggle/{product_id}")
async def toggle_wishlist(product_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_optional_user(request, db=db)
    if not user or user.email == settings.GUEST_EMAIL:
        return JSONResponse({"success": False, "message": "Login required"}, status_code=401)
    existing = await db.execute(select(WishlistItem).where(WishlistItem.user_id == user.id, WishlistItem.product_id == product_id))
    item = existing.scalar_one_or_none()
    if item:
        await db.delete(item)
        await db.commit()
        return JSONResponse({"success": True, "wishlisted": False})
    db.add(WishlistItem(user_id=user.id, product_id=product_id))
    await db.commit()
    return JSONResponse({"success": True, "wishlisted": True})


@router.get("/wishlist")
async def wishlist_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_optional_user(request, db=db)
    if not user or user.email == settings.GUEST_EMAIL:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    result = await db.execute(
        select(WishlistItem).where(WishlistItem.user_id == user.id).options(selectinload(WishlistItem.product))
    )
    items = result.scalars().all()
    return templates.TemplateResponse(
        request=request,
        name="store/wishlist.html",
        context={"items": items, "current_user": user, "is_authenticated": True},
    )


@router.get("/api/coupon/validate")
async def validate_coupon_api(code: str = Query(...), subtotal: float = Query(0), db: AsyncSession = Depends(get_db)):
    from app.services.order_service import apply_coupon
    discount, coupon = await apply_coupon(db, code, subtotal, {})
    if not coupon:
        return JSONResponse({"valid": False, "discount": 0})
    return JSONResponse({"valid": True, "discount": discount, "code": coupon.code})


@router.post("/orders/checkout")
async def checkout(
    request: Request,
    coupon_code: str = Form(""),
    db: AsyncSession = Depends(get_db),
    background_tasks: BackgroundTasks = None,
):
    user = await _resolve_storefront_user(request, db)
    if not user:
        raise HTTPException(status_code=404, detail="User session not found")
    order = await create_order_from_cart(db, user.id, coupon_code or None)
    if not order:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    if background_tasks:
        from app.core.background import invalidate_cache_async

        async def _clear():
            await invalidate_cache_async("products:*")

        background_tasks.add_task(_clear)
    logger.info("Order #%s placed by %s — $%.2f", order.id, user.email, order.total_amount)
    return RedirectResponse(url=f"/orders/{order.id}", status_code=status.HTTP_303_SEE_OTHER)
