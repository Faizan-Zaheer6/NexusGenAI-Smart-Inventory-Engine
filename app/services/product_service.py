import math
from typing import Optional

from datetime import datetime, timezone

from sqlalchemy import asc, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.cache import cache_delete_pattern, cache_get, cache_set
from app.core.config import get_settings
from app.database.models import FlashSale, Product, Review

settings = get_settings()


async def list_products(
    db: AsyncSession,
    page: int = 1,
    per_page: Optional[int] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    sort: str = "newest",
) -> tuple[list[dict], dict]:
    per_page = per_page or settings.PRODUCTS_PER_PAGE
    cache_key = f"products:{page}:{per_page}:{category}:{search}:{sort}"
    cached = await cache_get(cache_key)
    if cached:
        return cached["items"], cached["meta"]

    query = select(Product)
    if category and category != "all":
        query = query.where(Product.category == category)
    if search:
        like = f"%{search}%"
        query = query.where(or_(Product.name.ilike(like), Product.category.ilike(like)))

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    if sort == "price_asc":
        query = query.order_by(asc(Product.price))
    elif sort == "price_desc":
        query = query.order_by(desc(Product.price))
    elif sort == "stock":
        query = query.order_by(desc(Product.stock))
    else:
        query = query.order_by(desc(Product.created_at), desc(Product.id))

    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    products = result.scalars().all()

    now_items = []
    if products:
        product_ids = [p.id for p in products]
        now = datetime.now(timezone.utc)
        
        # Batch query 1: Fetch active flash sales for all products in one go
        flash_res = await db.execute(
            select(FlashSale).where(
                FlashSale.product_id.in_(product_ids),
                FlashSale.is_active.is_(True),
                FlashSale.ends_at > now,
            )
        )
        flash_map = {f.product_id: f for f in flash_res.scalars().all()}
        
        # Batch query 2: Fetch review aggregates (average rating and count) for all products in one go
        rev_res = await db.execute(
            select(
                Review.product_id,
                func.avg(Review.rating).label("avg_rating"),
                func.count(Review.id).label("review_count")
            )
            .where(Review.product_id.in_(product_ids))
            .group_by(Review.product_id)
        )
        reviews_map = {r.product_id: (r.avg_rating, r.review_count) for r in rev_res.all()}

        for p in products:
            flash = flash_map.get(p.id)
            price = p.price
            if flash:
                price = round(p.price * (1 - flash.discount_percent / 100), 2)
            
            avg_rating, review_count = reviews_map.get(p.id, (0.0, 0))
            
            now_items.append({
                "id": p.id,
                "name": p.name,
                "category": p.category,
                "price": p.price,
                "effective_price": price,
                "stock": p.stock,
                "image_url": p.image_url,
                "description": p.description,
                "gallery_urls": (p.gallery_urls or "").split("|") if p.gallery_urls else [p.image_url],
                "avg_rating": round(float(avg_rating or 0), 1),
                "review_count": review_count or 0,
                "flash_sale": {"discount_percent": flash.discount_percent, "ends_at": flash.ends_at.isoformat()} if flash else None,
            })

    meta = {
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": max(1, math.ceil(total / per_page)),
    }
    await cache_set(cache_key, {"items": now_items, "meta": meta})
    return now_items, meta


async def get_product_detail(db: AsyncSession, product_id: int) -> Optional[dict]:
    result = await db.execute(
        select(Product).where(Product.id == product_id).options(selectinload(Product.reviews))
    )
    product = result.scalar_one_or_none()
    if not product:
        return None
    flash_res = await db.execute(
        select(FlashSale).where(FlashSale.product_id == product.id, FlashSale.is_active.is_(True))
    )
    flash = flash_res.scalar_one_or_none()
    price = product.price
    if flash:
        price = round(product.price * (1 - flash.discount_percent / 100), 2)
    rev_res = await db.execute(select(func.avg(Review.rating), func.count(Review.id)).where(Review.product_id == product.id))
    avg_rating, review_count = rev_res.one()
    reviews_res = await db.execute(
        select(Review).where(Review.product_id == product.id).options(selectinload(Review.user)).order_by(Review.created_at.desc()).limit(10)
    )
    reviews = reviews_res.scalars().all()
    return {
        "id": product.id,
        "name": product.name,
        "category": product.category,
        "price": product.price,
        "effective_price": price,
        "stock": product.stock,
        "image_url": product.image_url,
        "description": product.description or f"Premium {product.category} item from NexusAI catalog.",
        "gallery_urls": (product.gallery_urls or "").split("|") if product.gallery_urls else [product.image_url],
        "avg_rating": round(float(avg_rating or 0), 1),
        "review_count": review_count or 0,
        "reviews": [
            {"id": r.id, "rating": r.rating, "comment": r.comment, "user": r.user.full_name, "created_at": r.created_at.isoformat()}
            for r in reviews
        ],
        "flash_sale": {"discount_percent": flash.discount_percent, "ends_at": flash.ends_at.isoformat()} if flash else None,
    }


async def invalidate_product_cache() -> None:
    await cache_delete_pattern("products:*")
