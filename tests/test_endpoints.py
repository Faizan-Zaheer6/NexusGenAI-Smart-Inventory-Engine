import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.database.connection import AsyncSessionLocal
from app.database.models import Product, User
from app.main import app


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest.mark.asyncio
async def test_homepage_returns_200(client: AsyncClient):
    response = await client.get("/")
    assert response.status_code == 200
    assert "NexusAI" in response.text or "Premium" in response.text


@pytest.mark.asyncio
async def test_register_login_token_pipeline(client: AsyncClient):
    email = f"pytest_{uuid.uuid4().hex[:10]}@example.com"
    password = "pytest_secure_pass_123"

    signup = await client.post(
        "/auth/signup",
        json={"email": email, "full_name": "Pytest User", "password": password},
    )
    assert signup.status_code == 200
    signup_body = signup.json()
    assert "access_token" in signup_body
    assert signup_body.get("token_type") == "bearer"

    login = await client.post(
        "/auth/login",
        json={"email": email, "password": password},
    )
    assert login.status_code == 200
    login_body = login.json()
    assert "access_token" in login_body
    assert isinstance(login_body["access_token"], str)
    assert len(login_body["access_token"]) > 20


@pytest.mark.asyncio
async def test_storefront_product_and_cart_allocation(client: AsyncClient):
    async with AsyncSessionLocal() as session:
        product_res = await session.execute(select(Product).where(Product.stock > 0).limit(1))
        product = product_res.scalar_one_or_none()
        assert product is not None, "Seeded catalog must contain in-stock products"

    login = await client.post(
        "/auth/login",
        json={"email": "guest@nexusai.com", "password": "guestpassword"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    detail = await client.get(f"/api/v1/products/{product.id}", headers={"Authorization": f"Bearer {token}"})
    if detail.status_code == 404:
        list_res = await client.get("/api/v1/products?page=1", headers={"Authorization": f"Bearer {token}"})
        assert list_res.status_code == 200
        body = list_res.json()
        items = body.get("data") or []
        assert len(items) > 0
        product_id = items[0]["id"]
    else:
        assert detail.status_code == 200
        product_id = product.id

    add_res = await client.post(
        f"/cart/add/{product_id}",
        headers={"Authorization": f"Bearer {token}", "X-Requested-With": "XMLHttpRequest"},
    )
    assert add_res.status_code == 200
    cart_payload = add_res.json()
    assert cart_payload.get("success") is True
    assert cart_payload.get("cart", {}).get("total_items", 0) >= 1


@pytest.mark.asyncio
async def test_admin_route_blocks_unauthenticated_guest(client: AsyncClient):
    response = await client.get("/admin", follow_redirects=False)
    assert response.status_code in (401, 403, 303)
    if response.status_code == 303:
        assert "/admin/login" in response.headers.get("location", "")

    api_admin = await client.get("/admin/export/excel", follow_redirects=False)
    assert api_admin.status_code in (401, 403, 303)
