import os
from fastapi import APIRouter, Depends, Request, HTTPException, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from nexus_ai.database.connection import get_db
from nexus_ai.database.models import Product, CartItem
from nexus_ai.dependencies import admin_required

router = APIRouter()

# Templates directory (app/templates) relative to project root
TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "app", "templates")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

@router.get("/", response_class=RedirectResponse, include_in_schema=False)
async def root_redirect():
    return RedirectResponse(url="/store")

@router.get("/store")
async def read_storefront(request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Product))
    products = result.scalars().all()
    return templates.TemplateResponse(
        request=request,
        name="store/shop.html",
        context={
            "products": products,
            "current_user": {"full_name": "Guest"},
            "filters": {"search": "", "category": "all", "sort": "newest", "page": 1},
        },
    )

@router.get("/admin", dependencies=[Depends(admin_required)])
async def read_admin_dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Product))
    products = result.scalars().all()
    low_stock = sum(1 for p in products if p.stock < 5)
    total_sales = 0  # placeholder for future aggregation
    return templates.TemplateResponse(
        request=request,
        name="admin/dashboard.html",
        context={
            "products": products,
            "low_stock_count": low_stock,
            "sales_total": f"${total_sales:,.2f}",
            "user_count": 0,
            "current_user": {"full_name": "Admin"},
        },
    )

# Stock adjustment endpoints – POST with redirect back to admin panel
@router.post("/admin/stock/add/{product_id}")
async def add_stock(product_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    product.stock += 1
    await db.commit()
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)

@router.post("/admin/stock/reduce/{product_id}")
async def reduce_stock(product_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    if product.stock > 0:
        product.stock -= 1
        await db.commit()
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)

# API endpoint for AJAX fetching (optional)
@router.get("/api/products")
async def api_products(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Product))
    products = result.scalars().all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "category": p.category,
            "price": float(p.price),
            "stock": p.stock,
            "image_url": p.image_url,
        }
        for p in products
    ]
