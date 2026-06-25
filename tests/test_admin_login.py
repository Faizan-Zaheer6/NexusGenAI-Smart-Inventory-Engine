import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from app.main import app

@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac

@pytest.mark.asyncio
async def test_admin_login_success(client: AsyncClient):
    """
    Verifies that the /auth/admin/login endpoint accepts the username 'admin'
    and password 'SecureAdminTest2026!', returning a successful HTTP 200 and a token.
    """
    response = await client.post(
        "/auth/admin/login",
        json={"email": "admin", "password": "SecureAdminTest2026!"}
    )
    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body
    assert body.get("token_type") == "bearer"

@pytest.mark.asyncio
async def test_admin_login_email_success(client: AsyncClient):
    """
    Verifies that the /auth/admin/login endpoint accepts the email 'admin@nexusai.com'
    and password 'SecureAdminTest2026!', returning a successful HTTP 200 and a token.
    """
    response = await client.post(
        "/auth/admin/login",
        json={"email": "admin@nexusai.com", "password": "SecureAdminTest2026!"}
    )
    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body
    assert body.get("token_type") == "bearer"
