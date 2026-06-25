from fastapi import APIRouter

from app.routers.api.v1 import ai, coupons, orders, products

router = APIRouter(prefix="/api/v1")
router.include_router(products.router)
router.include_router(orders.router)
router.include_router(coupons.router)
router.include_router(ai.router)
