from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class AIQueryRequest(BaseModel):
    user_message: str = Field(..., min_length=1, max_length=2000)
    message: Optional[str] = Field(None, max_length=2000)
    mode: Literal["assistant", "analytics"] = "assistant"
    session_id: Optional[str] = Field(None, description="Unique chat session ID")



class QueryResponse(BaseModel):
    mode: str
    answer: str
    sql_query: Optional[str] = None
    rows: Optional[list[dict[str, Any]]] = None
    row_count: int = 0
    meta: dict[str, Any] = Field(default_factory=dict)
