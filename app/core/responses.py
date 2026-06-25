from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class APIError(BaseModel):
    code: str
    message: str
    field: Optional[str] = None


class APIMeta(BaseModel):
    page: Optional[int] = None
    per_page: Optional[int] = None
    total: Optional[int] = None
    total_pages: Optional[int] = None


class APIResponse(BaseModel, Generic[T]):
    data: T
    meta: Optional[APIMeta] = None
    errors: list[APIError] = []


def success(data: Any, meta: Optional[dict] = None) -> dict:
    return {"data": data, "meta": meta or {}, "errors": []}


def error(message: str, code: str = "ERROR", field: Optional[str] = None) -> dict:
    return {"data": None, "meta": {}, "errors": [{"code": code, "message": message, "field": field}]}
