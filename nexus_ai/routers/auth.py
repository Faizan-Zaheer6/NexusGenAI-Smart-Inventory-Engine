import os
from datetime import timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr

from nexus_ai.database.connection import get_db
from nexus_ai.database import models
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from nexus_ai.auth import create_access_token, decode_access_token, get_password_hash, verify_password

router = APIRouter()

class UserCreate(BaseModel):
    email: EmailStr
    full_name: str
    password: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class AdminLogin(BaseModel):
    email: Optional[str] = None
    username: Optional[str] = None
    password: str

@router.post("/signup", response_model=dict)
async def signup(user: UserCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.User).where(models.User.email == user.email))
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
    hashed_pw = get_password_hash(user.password)
    new_user = models.User(email=user.email, full_name=user.full_name, hashed_password=hashed_pw)
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    token = create_access_token({"sub": str(new_user.id), "name": new_user.full_name, "admin": new_user.is_admin})
    return {"access_token": token, "token_type": "bearer"}

@router.post("/login", response_model=dict)
async def login(credentials: UserLogin, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.User).where(models.User.email == credentials.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = create_access_token({"sub": str(user.id), "name": user.full_name, "admin": user.is_admin})
    return {"access_token": token, "token_type": "bearer"}

@router.post("/admin/login", response_model=dict)
async def admin_login(payload: AdminLogin, db: AsyncSession = Depends(get_db)):
    email = payload.email or "admin@nexusai.com"
    if email == "admin" or payload.username == "admin":
        email = "admin@nexusai.com"
    result = await db.execute(select(models.User).where(models.User.email == email))
    admin_user = result.scalar_one_or_none()
    if not admin_user or not admin_user.is_admin:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin credentials")
    if not verify_password(payload.password, admin_user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin credentials")
    token = create_access_token({"sub": str(admin_user.id), "name": admin_user.full_name, "admin": True})
    return {"access_token": token, "token_type": "bearer"}
