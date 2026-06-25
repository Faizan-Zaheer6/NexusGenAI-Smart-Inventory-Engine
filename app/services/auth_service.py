from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import log_audit
from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    generate_password_reset_token,
    generate_refresh_token,
    get_password_hash,
    hash_token,
    password_reset_expires_at,
    refresh_token_expires_at,
    verify_password,
)
from app.database.models import RefreshToken, User

settings = get_settings()


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def check_account_lockout(user: User) -> None:
    if user.locked_until and user.locked_until > datetime.now(timezone.utc):
        remaining = int((user.locked_until - datetime.now(timezone.utc)).total_seconds() / 60) + 1
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=f"Account locked. Try again in {remaining} minute(s).",
        )


async def record_failed_login(db: AsyncSession, user: Optional[User], request: Request) -> None:
    if not user:
        return
    user.failed_login_attempts += 1
    if user.failed_login_attempts >= settings.MAX_LOGIN_ATTEMPTS:
        user.locked_until = datetime.now(timezone.utc) + __import__("datetime").timedelta(
            minutes=settings.LOCKOUT_MINUTES
        )
        await log_audit(
            db,
            action="account_locked",
            entity_type="user",
            entity_id=user.id,
            details=f"Locked after {settings.MAX_LOGIN_ATTEMPTS} failed attempts",
            user_id=user.id,
            ip_address=_client_ip(request),
        )
    await db.commit()


async def reset_failed_login(db: AsyncSession, user: User) -> None:
    user.failed_login_attempts = 0
    user.locked_until = None
    await db.commit()


async def authenticate_user(
    db: AsyncSession,
    email: str,
    password: str,
    request: Request,
) -> User:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    await check_account_lockout(user)
    if not verify_password(password, user.hashed_password):
        await record_failed_login(db, user, request)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    await reset_failed_login(db, user)
    return user


def build_access_token(user: User) -> str:
    return create_access_token({"sub": str(user.id), "name": user.full_name, "admin": user.is_admin})


async def issue_token_pair(db: AsyncSession, user: User) -> dict:
    access = build_access_token(user)
    refresh = generate_refresh_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_token(refresh),
            expires_at=refresh_token_expires_at(),
        )
    )
    await db.commit()
    return {"access_token": access, "refresh_token": refresh, "token_type": "bearer"}


async def rotate_refresh_token(db: AsyncSession, refresh_token: str) -> dict:
    token_hash = hash_token(refresh_token)
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash, RefreshToken.revoked.is_(False))
    )
    stored = result.scalar_one_or_none()
    if not stored or stored.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    stored.revoked = True
    user_result = await db.execute(select(User).where(User.id == stored.user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return await issue_token_pair(db, user)


async def revoke_refresh_tokens(db: AsyncSession, user_id: int) -> None:
    result = await db.execute(select(RefreshToken).where(RefreshToken.user_id == user_id, RefreshToken.revoked.is_(False)))
    for token in result.scalars().all():
        token.revoked = True
    await db.commit()


async def create_password_reset(db: AsyncSession, email: str) -> Optional[str]:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user:
        return None
    token = generate_password_reset_token()
    user.password_reset_token = hash_token(token)
    user.password_reset_expires = password_reset_expires_at()
    await db.commit()
    return token


async def reset_password_with_token(db: AsyncSession, token: str, new_password: str) -> bool:
    token_hash = hash_token(token)
    result = await db.execute(select(User).where(User.password_reset_token == token_hash))
    user = result.scalar_one_or_none()
    if not user or not user.password_reset_expires or user.password_reset_expires < datetime.now(timezone.utc):
        return False
    user.hashed_password = get_password_hash(new_password)
    user.password_reset_token = None
    user.password_reset_expires = None
    user.failed_login_attempts = 0
    user.locked_until = None
    await revoke_refresh_tokens(db, user.id)
    await db.commit()
    return True
