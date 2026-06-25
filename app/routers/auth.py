from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import get_settings
from app.core.logger import logger
from app.core.security import get_password_hash
from app.database.connection import get_db
from app.database.models import User
from app.schemas.auth import AdminLogin, TokenResponse, UserCreate, UserLogin
from app.services.auth_service import (
    authenticate_user,
    build_access_token,
    create_password_reset,
    issue_token_pair,
    reset_password_with_token,
    revoke_refresh_tokens,
    rotate_refresh_token,
)

settings = get_settings()
limiter = Limiter(key_func=get_remote_address)
TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

api_router = APIRouter(tags=["Authentication API"])
pages_router = APIRouter(tags=["Authentication Pages"])


class RefreshRequest(BaseModel):
    refresh_token: str


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str


async def _set_auth_cookie(db: AsyncSession, response: RedirectResponse, user: User) -> RedirectResponse:
    from app.services.auth_service import issue_token_pair
    tokens = await issue_token_pair(db, user)
    response.set_cookie(
        key="access_token",
        value=tokens["access_token"],
        httponly=True,
        samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    response.set_cookie(
        key="refresh_token",
        value=tokens["refresh_token"],
        httponly=True,
        samesite="lax",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
    )
    return response


@api_router.post("/signup", response_model=dict)
@limiter.limit(settings.RATE_LIMIT_SIGNUP)
async def api_signup(request: Request, payload: UserCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == payload.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(email=payload.email, full_name=payload.full_name, hashed_password=get_password_hash(payload.password), is_admin=False, role="customer")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    tokens = await issue_token_pair(db, user)
    try:
        from app.services.email_service import send_welcome_email
        from app.core.background import run_background
        run_background(send_welcome_email(user.email, user.full_name))
    except Exception as e:
        logger.error("Failed to queue welcome email: %s", e)
    return tokens


@api_router.post("/login", response_model=dict)
@limiter.limit(settings.RATE_LIMIT_LOGIN)
async def api_login(request: Request, credentials: UserLogin, db: AsyncSession = Depends(get_db)):
    user = await authenticate_user(db, credentials.email, credentials.password, request)
    return await issue_token_pair(db, user)


@api_router.post("/admin/login", response_model=dict)
@limiter.limit(settings.RATE_LIMIT_LOGIN)
async def api_admin_login(request: Request, payload: AdminLogin, db: AsyncSession = Depends(get_db)):
    email = payload.email
    if email == "admin":
        email = "admin@nexusai.com"
    result = await db.execute(select(User).where(User.email == email, User.is_admin.is_(True)))
    admin_user = result.scalar_one_or_none()
    if not admin_user:
        raise HTTPException(status_code=401, detail="Invalid admin credentials")
    user = await authenticate_user(db, email, payload.password, request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Not an administrator")
    return await issue_token_pair(db, user)


@api_router.post("/refresh")
async def api_refresh(payload: RefreshRequest, db: AsyncSession = Depends(get_db)):
    return await rotate_refresh_token(db, payload.refresh_token)


@api_router.post("/logout")
async def api_logout(request: Request, db: AsyncSession = Depends(get_db)):
    from app.dependencies import get_optional_user
    user = await get_optional_user(request, db=db)
    if user:
        await revoke_refresh_tokens(db, user.id)
    return {"message": "Logged out"}


@api_router.post("/forgot-password")
@limiter.limit("3/minute")
async def api_forgot_password(request: Request, payload: PasswordResetRequest, db: AsyncSession = Depends(get_db)):
    token = await create_password_reset(db, payload.email)
    if token:
        user_res = await db.execute(select(User).where(User.email == payload.email))
        user = user_res.scalar_one_or_none()
        if user:
            from app.core.background import run_background
            from app.services.email_service import send_password_reset
            run_background(send_password_reset(user.email, user.full_name, token))
    return {"message": "If the email exists, a reset link has been sent."}


@api_router.post("/reset-password")
async def api_reset_password(payload: PasswordResetConfirm, db: AsyncSession = Depends(get_db)):
    ok = await reset_password_with_token(db, payload.token, payload.new_password)
    if not ok:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    return {"message": "Password updated successfully"}


@pages_router.get("/login")
async def show_login(request: Request):
    return templates.TemplateResponse(request=request, name="auth/login.html", context={"error": None})


@pages_router.get("/signup")
async def show_signup(request: Request):
    return templates.TemplateResponse(request=request, name="auth/signup.html", context={"error": None})


@pages_router.get("/forgot-password")
async def show_forgot_password(request: Request):
    return templates.TemplateResponse(request=request, name="auth/forgot_password.html", context={"error": None, "success": None, "reset_link": None})


@pages_router.get("/reset-password")
async def show_reset_password(request: Request, token: str = ""):
    return templates.TemplateResponse(request=request, name="auth/reset_password.html", context={"error": None, "token": token})


@pages_router.post("/signup")
@limiter.limit(settings.RATE_LIMIT_SIGNUP)
async def process_signup(request: Request, full_name: str = Form(...), email: str = Form(...), password: str = Form(...), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == email))
    if result.scalar_one_or_none():
        return templates.TemplateResponse(request=request, name="auth/signup.html", context={"error": "Email already registered"})
    user = User(email=email, full_name=full_name, hashed_password=get_password_hash(password), is_admin=False, role="customer")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    try:
        from app.services.email_service import send_welcome_email
        from app.core.background import run_background
        run_background(send_welcome_email(user.email, user.full_name))
    except Exception as e:
        logger.error("Failed to queue welcome email: %s", e)
    return await _set_auth_cookie(db, response, user)


@pages_router.post("/login")
@limiter.limit(settings.RATE_LIMIT_LOGIN)
async def process_login(request: Request, email: str = Form(...), password: str = Form(...), db: AsyncSession = Depends(get_db)):
    try:
        user = await authenticate_user(db, email, password, request)
    except HTTPException:
        return templates.TemplateResponse(request=request, name="auth/login.html", context={"error": "Invalid email or password"})
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    return await _set_auth_cookie(db, response, user)


@pages_router.post("/forgot-password")
@limiter.limit("3/minute")
async def process_forgot_password(request: Request, email: str = Form(...), db: AsyncSession = Depends(get_db)):
    token = await create_password_reset(db, email)
    reset_link = f"/reset-password?token={token}" if token else None
    if token:
        user_res = await db.execute(select(User).where(User.email == email))
        user = user_res.scalar_one_or_none()
        if user:
            from app.core.background import run_background
            from app.services.email_service import send_password_reset
            run_background(send_password_reset(user.email, user.full_name, token))
    return templates.TemplateResponse(
        request=request,
        name="auth/forgot_password.html",
        context={
            "error": None,
            "success": "If your email is registered, check your inbox for the reset link.",
            "reset_link": reset_link if settings.DEBUG else None,
        },
    )


@pages_router.post("/reset-password")
async def process_reset_password(request: Request, token: str = Form(...), new_password: str = Form(...), db: AsyncSession = Depends(get_db)):
    ok = await reset_password_with_token(db, token, new_password)
    if not ok:
        return templates.TemplateResponse(request=request, name="auth/reset_password.html", context={"error": "Invalid or expired token", "token": token})
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)


@pages_router.get("/admin/login")
async def show_admin_login(request: Request):
    return templates.TemplateResponse(request=request, name="auth/admin_login.html", context={"error": None})
@pages_router.post("/admin/login")
@limiter.limit(settings.RATE_LIMIT_LOGIN)
async def process_admin_login(request: Request, email: str = Form(...), password: str = Form(...), db: AsyncSession = Depends(get_db)):
    try:
        user = await authenticate_user(db, email, password, request)
    except HTTPException:
        return templates.TemplateResponse(request=request, name="auth/admin_login.html", context={"error": "Invalid administrator credentials"})
    if user.role not in ("admin", "manager"):
        return templates.TemplateResponse(request=request, name="auth/admin_login.html", context={"error": "Not an administrator account"})
    response = RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)
    return await _set_auth_cookie(db, response, user)


@pages_router.get("/logout")
async def logout(request: Request, db: AsyncSession = Depends(get_db)):
    from app.dependencies import get_optional_user
    user = await get_optional_user(request, db=db)
    if user:
        await revoke_refresh_tokens(db, user.id)
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    return response
