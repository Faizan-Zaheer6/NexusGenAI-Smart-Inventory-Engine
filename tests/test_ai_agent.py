import uuid
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from app.database.connection import AsyncSessionLocal
from app.database.models import ChatSession, ChatMessage
from app.main import app


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest.mark.asyncio
async def test_ai_query_with_session_memory(client: AsyncClient):
    session_id = f"test_sess_{uuid.uuid4().hex[:10]}"
    
    # 1. Ask a question
    response1 = await client.post(
        "/api/v1/ai/query",
        json={
            "user_message": "Hello, is anyone there?",
            "mode": "assistant",
            "session_id": session_id
        }
    )
    assert response1.status_code == 200
    res_data1 = response1.json()
    assert "data" in res_data1
    assert "answer" in res_data1["data"]
    
    # 2. Check if ChatSession and ChatMessage are stored in DB
    async with AsyncSessionLocal() as session:
        stmt_sess = select(ChatSession).where(ChatSession.session_id == session_id)
        sess_res = await session.execute(stmt_sess)
        sess = sess_res.scalar_one_or_none()
        assert sess is not None, "ChatSession should be created"
        
        stmt_msgs = select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.id.asc())
        msgs_res = await session.execute(stmt_msgs)
        msgs = msgs_res.scalars().all()
        assert len(msgs) == 2, "There should be exactly 2 messages (user + assistant)"
        assert msgs[0].role == "user"
        assert msgs[0].content == "Hello, is anyone there?"
        assert msgs[1].role == "assistant"
        
    # 3. Send a follow-up query to check if memory is loaded
    response2 = await client.post(
        "/api/v1/ai/query",
        json={
            "user_message": "Who are you again?",
            "mode": "assistant",
            "session_id": session_id
        }
    )
    assert response2.status_code == 200
    res_data2 = response2.json()
    assert "answer" in res_data2["data"]
    
    # 4. Check if 4 messages exist in DB now
    async with AsyncSessionLocal() as session:
        stmt_msgs = select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.id.asc())
        msgs_res = await session.execute(stmt_msgs)
        msgs = msgs_res.scalars().all()
        assert len(msgs) == 4, "There should be exactly 4 messages now (2 user + 2 assistant)"
        assert msgs[2].content == "Who are you again?"
