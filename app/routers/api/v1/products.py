from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.responses import success
from app.database.connection import get_db
from app.database.models import Product, Review, User, WishlistItem
from app.dependencies import get_current_user, get_optional_user
from app.services.order_service import get_frequently_bought_together
from app.services.product_service import get_product_detail, list_products
from fastapi import Request

router = APIRouter(prefix="/products", tags=["API v1 - Products"])


@router.get("")
async def api_list_products(
    page: int = Query(1, ge=1),
    per_page: int = Query(12, ge=1, le=48),
    category: str = Query("all"),
    search: str = Query(""),
    sort: str = Query("newest"),
    db: AsyncSession = Depends(get_db),
):
    items, meta = await list_products(db, page, per_page, category if category != "all" else None, search or None, sort)
    return success(items, meta)


@router.get("/categories")
async def api_categories(db: AsyncSession = Depends(get_db)):
    from sqlalchemy import func

    result = await db.execute(select(Product.category, func.count(Product.id)).group_by(Product.category).order_by(Product.category))
    cats = [{"name": row[0], "count": row[1]} for row in result.all()]
    return success(cats)


@router.get("/wishlist/mine")
async def api_my_wishlist(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    result = await db.execute(
        select(WishlistItem).where(WishlistItem.user_id == user.id).options(selectinload(WishlistItem.product))
    )
    items = [
        {"id": w.product.id, "name": w.product.name, "price": w.product.price, "image_url": w.product.image_url}
        for w in result.scalars().all()
    ]
    return success(items)


@router.get("/{product_id}")
async def api_product_detail(product_id: int, db: AsyncSession = Depends(get_db)):
    detail = await get_product_detail(db, product_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Product not found")
    fbt = await get_frequently_bought_together(db, product_id)
    detail["frequently_bought_together"] = [{"id": p.id, "name": p.name, "price": p.price, "image_url": p.image_url} for p in fbt]
    return success(detail)


class ReviewCreate(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str = Field(default="", max_length=1000)


@router.post("/{product_id}/reviews")
async def api_add_review(
    product_id: int,
    payload: ReviewCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    prod = await db.execute(select(Product).where(Product.id == product_id))
    if not prod.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Product not found")
    existing = await db.execute(select(Review).where(Review.user_id == user.id, Review.product_id == product_id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="You already reviewed this product")
    review = Review(user_id=user.id, product_id=product_id, rating=payload.rating, comment=payload.comment)
    db.add(review)
    await db.commit()
    return success({"id": review.id, "rating": review.rating, "comment": review.comment})


@router.post("/{product_id}/wishlist")
async def api_add_wishlist(product_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    prod = await db.execute(select(Product).where(Product.id == product_id))
    if not prod.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Product not found")
    existing = await db.execute(select(WishlistItem).where(WishlistItem.user_id == user.id, WishlistItem.product_id == product_id))
    if existing.scalar_one_or_none():
        return success({"message": "Already in wishlist"})
    db.add(WishlistItem(user_id=user.id, product_id=product_id))
    await db.commit()
    return success({"message": "Added to wishlist"})


@router.delete("/{product_id}/wishlist")
async def api_remove_wishlist(product_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    result = await db.execute(select(WishlistItem).where(WishlistItem.user_id == user.id, WishlistItem.product_id == product_id))
    item = result.scalar_one_or_none()
    if item:
        await db.delete(item)
        await db.commit()
    return success({"message": "Removed from wishlist"})

