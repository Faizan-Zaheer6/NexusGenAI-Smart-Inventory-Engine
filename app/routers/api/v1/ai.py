from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.responses import success
from app.database.connection import get_db
from app.database.models import User
from app.dependencies import get_optional_user
from app.schemas.ai import AIQueryRequest, QueryResponse
from app.services.ai_service import FORBIDDEN_SQL, process_ai_query

router = APIRouter(prefix="/ai", tags=["AI Agent"])


def _validate_message_guardrails(message: str) -> None:
    if FORBIDDEN_SQL.search(message):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message contains blocked SQL keywords.",
        )


@router.post("/query", response_model=dict)
async def ai_query(
    request: AIQueryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Annotated[Optional[User], Depends(get_optional_user)] = None,
) -> dict:
    # Handle both fields dynamically
    user_msg = request.user_message if request.user_message else (request.message or "")
    _validate_message_guardrails(user_msg)

    if request.mode == "analytics":
        if not current_user or not current_user.is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Analytics mode requires an authenticated admin account.",
            )

    result: QueryResponse = await process_ai_query(db, user_msg, request.mode, request.session_id)
    return success(result.model_dump(), meta={"mode": request.mode})

