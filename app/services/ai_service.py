import asyncio
import json
import re
from decimal import Decimal
from typing import Any, Optional, TypedDict, List

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logger import logger
from app.schemas.ai import QueryResponse
from app.services.product_service import list_products
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langgraph.graph import StateGraph, END

settings = get_settings()

_vector_store = None


async def init_vector_store(db_session: AsyncSession):
    global _vector_store
    from sqlalchemy import select
    from app.database.models import Product

    try:
        result = await db_session.execute(select(Product))
        products = result.scalars().all()
        if not products:
            logger.warning("No products found to index in FAISS.")
            return

        documents = []
        for p in products:
            text_content = (
                f"Product: {p.name}, Category: {p.category}, Price: ${p.price:.2f}, "
                f"Stock: {p.stock} units. Description: {p.description or ''}"
            )
            doc = Document(
                page_content=text_content,
                metadata={"id": p.id, "name": p.name, "category": p.category, "price": p.price, "stock": p.stock}
            )
            documents.append(doc)

        from langchain_core.embeddings import Embeddings

        class SimpleEmbeddings(Embeddings):
            def embed_documents(self, texts: list[str]) -> list[list[float]]:
                vectors = []
                for t in texts:
                    vec = [0.0] * 768
                    for i, char in enumerate(t[:768]):
                        vec[i] = float(ord(char)) / 255.0
                    vectors.append(vec)
                return vectors

            def embed_query(self, text: str) -> list[float]:
                vec = [0.0] * 768
                for i, char in enumerate(text[:768]):
                    vec[i] = float(ord(char)) / 255.0
                return vec

        if not settings.GEMINI_API_KEY:
            logger.warning("GEMINI_API_KEY not found. Using local SimpleEmbeddings for FAISS RAG.")
            embeddings = SimpleEmbeddings()
        else:
            from langchain_google_genai import GoogleGenAIEmbeddings
            embeddings = GoogleGenAIEmbeddings(
                model="models/text-embedding-004",
                google_api_key=settings.GEMINI_API_KEY
            )

        def _build():
            return FAISS.from_documents(documents, embeddings)

        _vector_store = await asyncio.to_thread(_build)
        logger.info("FAISS vector store successfully initialized with %d products.", len(documents))
    except Exception as exc:
        logger.error("Failed to initialize FAISS vector store: %s", exc, exc_info=True)


FORBIDDEN_SQL = re.compile(
    r"\b(DROP|DELETE|UPDATE|TRUNCATE|INSERT|ALTER|CREATE|GRANT|REVOKE|EXEC|EXECUTE|MERGE|CALL)\b",
    re.IGNORECASE,
)

SCHEMA_METADATA = """
PostgreSQL schema (read-only SELECT queries only):
- users(id, full_name, email, is_admin, role, created_at)
- products(id, name, category, price, stock, created_at)
- cart_items(id, user_id, product_id, quantity)
- orders(id, user_id, subtotal, discount_amount, total_amount, status, coupon_code, created_at)
- order_items(id, order_id, product_id, quantity, unit_price)
- warehouses(id, name, location, is_active)
- warehouse_stocks(id, warehouse_id, product_id, quantity)
- coupons(id, code, discount_type, discount_value, is_active)
- reviews(id, product_id, user_id, rating, comment, created_at)
- audit_logs(id, user_id, action, entity_type, entity_id, details, created_at)
"""

_ASSISTANT_SYSTEM = """
You are NexusAI Store Assistant for an enterprise inventory storefront.
Respond in friendly Roman Urdu mixed with English when helpful (e.g. "Aap ke liye best option yeh hai...").
Keep answers concise, safe, and helpful about products, stock, orders, and recommendations.
Never reveal secrets, SQL, or internal credentials. If unsure, suggest browsing the storefront.
"""

_ANALYTICS_SYSTEM = f"""
You are NexusAI Analytics Agent. Generate ONLY a single PostgreSQL SELECT statement.
Rules:
- SELECT only. No comments. No markdown fences. No explanation text.
- Use only tables/columns from this schema:
{SCHEMA_METADATA}
- Prefer aggregates (COUNT, SUM, AVG) and LIMIT 100 for large result sets.
- Return raw SQL only.
"""


def _guard_sql(sql: str) -> str:
    cleaned = sql.strip().rstrip(";")
    if FORBIDDEN_SQL.search(cleaned):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Blocked: only read-only SELECT queries are permitted.",
        )
    upper = cleaned.upper()
    if not upper.startswith("SELECT"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only SELECT statements are allowed in analytics mode.",
        )
    if ";" in cleaned:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Multiple SQL statements are not allowed.",
        )
    return cleaned


def _serialize_row(row: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, value in row._mapping.items():
        if isinstance(value, Decimal):
            payload[key] = float(value)
        elif hasattr(value, "isoformat"):
            payload[key] = value.isoformat()
        else:
            payload[key] = value
    return payload


async def _gemini_generate(prompt: str, system_instruction: str) -> str:
    if not settings.GEMINI_API_KEY:
        return ""

    def _call() -> str:
        import google.generativeai as genai

        genai.configure(api_key=settings.GEMINI_API_KEY)
        model = genai.GenerativeModel(
            model_name=settings.GEMINI_MODEL,
            system_instruction=system_instruction,
        )
        response = model.generate_content(prompt)
        return (response.text or "").strip()

    try:
        return await asyncio.to_thread(_call)
    except Exception as exc:
        logger.error("Gemini API call failed: %s", exc, exc_info=True)
        return ""


async def _assistant_fallback(db: AsyncSession, message: str) -> str:
    items, meta = await list_products(db, page=1, per_page=5, search=message if len(message) > 2 else None)
    if items:
        lines = [f"• {p['name']} ({p['category']}) — ${p['effective_price']:.2f}, stock: {p['stock']}" for p in items]
        return (
            "Assalam o Alaikum! Main NexusAI assistant hoon.\n"
            "Yeh kuch products hain jo aap ke query se match karte hain:\n\n"
            + "\n".join(lines)
            + f"\n\nTotal catalog pages: {meta.get('total_pages', 1)}. Browse / for more!"
        )
    
    # If no items matched but they asked about stock/products, return an Urdu lookup error instead of greeting loop
    lower_message = message.lower()
    if any(word in lower_message for word in ["stock", "product", "price", "kitna", "hai", "h", "available", "mili", "watch", "mobile", "smartwatch"]):
        return (
            "Assalam o Alaikum! Mujhe aap ki query ke mutabiq koi product ya stock levels nahi mile. "
            "Please check product name ya storefront par manually browse karein."
        )

    return (
        "Assalam o Alaikum! Main NexusAI Agent hoon. Communicate in a mix of Roman Urdu and English. "
        "Aap stock, categories, ya product recommendations pooch sakte hain. "
        "Storefront par search/filter use karein ya mujh se specific product name poochien."
    )


async def _call_llm(prompt: str, system_instruction: str, history_messages: list) -> str:
    import httpx
    
    # 1. Gemini Provider (via LangChain langchain_google_genai)
    if settings.LLM_PROVIDER == "gemini":
        if not settings.GEMINI_API_KEY:
            return ""
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

            llm = ChatGoogleGenerativeAI(
                model=settings.GEMINI_MODEL,
                google_api_key=settings.GEMINI_API_KEY,
                temperature=0.7
            )
            messages = [SystemMessage(content=system_instruction)]
            for m in history_messages:
                if m["role"] == "user":
                    messages.append(HumanMessage(content=m["content"]))
                else:
                    messages.append(AIMessage(content=m["content"]))
            messages.append(HumanMessage(content=prompt))
            
            response = await llm.ainvoke(messages)
            return str(response.content)
        except Exception as e:
            logger.error("LangChain Gemini call failed: %s", e)
            return ""

    # 2. Groq Provider (via direct HTTP request to OpenAI-compatible endpoint)
    elif settings.LLM_PROVIDER == "groq":
        if not settings.GROQ_API_KEY:
            logger.error("GROQ_API_KEY is not set.")
            return ""
        try:
            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {settings.GROQ_API_KEY}",
                "Content-Type": "application/json"
            }
            messages = [{"role": "system", "content": system_instruction}]
            for m in history_messages:
                messages.append({"role": m["role"], "content": m["content"]})
            messages.append({"role": "user", "content": prompt})

            payload = {
                "model": settings.GROQ_MODEL,
                "messages": messages,
                "temperature": 0.7
            }
            async with httpx.AsyncClient() as client:
                res = await client.post(url, json=payload, headers=headers, timeout=30.0)
                if res.status_code == 200:
                    data = res.json()
                    return data["choices"][0]["message"]["content"]
                else:
                    logger.error("Groq API error: %d - %s", res.status_code, res.text)
                    return ""
        except Exception as e:
            logger.error("Groq API request failed: %s", e)
            return ""

    # 3. Local Ollama Provider (via native endpoint)
    elif settings.LLM_PROVIDER == "ollama":
        try:
            url = f"{settings.OLLAMA_HOST}/api/chat"
            messages = [{"role": "system", "content": system_instruction}]
            for m in history_messages:
                messages.append({"role": m["role"], "content": m["content"]})
            messages.append({"role": "user", "content": prompt})

            payload = {
                "model": settings.OLLAMA_MODEL,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": 0.7
                }
            }
            async with httpx.AsyncClient() as client:
                res = await client.post(url, json=payload, timeout=30.0)
                if res.status_code == 200:
                    data = res.json()
                    return data["message"]["content"]
                else:
                    logger.error("Ollama API error: %d - %s", res.status_code, res.text)
                    return ""
        except Exception as e:
            logger.error("Ollama local connection failed: %s", e)
            return ""

    return ""


# State definition for LangGraph
class AgentState(TypedDict):
    message: str
    session_id: Optional[str]
    history: List[dict]
    retrieved_context: str
    tool_output: str
    response: str


# Node 1: RAG context search in FAISS
async def retrieve_context_node(state: AgentState) -> dict:
    global _vector_store
    msg = state["message"].lower()
    context = ""
    # Only run retrieval if there's vector store and the prompt is related to catalog/products/recommendations
    if _vector_store and any(word in msg for word in ["product", "mili", "stock", "price", "check", "recommend", "show", "watch", "mobile", "smartwatch", "available", "laptops", "shoes", "wear", "items"]):
        try:
            def _search():
                return _vector_store.similarity_search(state["message"], k=3)
            docs = await asyncio.to_thread(_search)
            if docs:
                context = "\n".join([d.page_content for d in docs])
        except Exception as e:
            logger.error("FAISS search failed: %s", e)
    return {"retrieved_context": context}


# Node 2: Database checking (Tool) if user asks about stock/price
async def run_tool_node(state: AgentState) -> dict:
    msg = state["message"].lower()
    tool_out = ""
    if any(word in msg for word in ["stock", "price", "quantity", "units", "kitna", "mili", "available", "watch", "mobile", "smartwatch", "laptop", "shoe", "item"]):
        words = [w for w in state["message"].split() if len(w) > 2]
        from app.database.connection import AsyncSessionLocal
        from app.database.models import Product
        from sqlalchemy import select
        
        async def _query():
            async with AsyncSessionLocal() as session:
                found_products = []
                for w in words:
                    clean_w = w.strip("?,.! ")
                    if len(clean_w) < 3:
                        continue
                    stmt = select(Product).where(Product.name.ilike(f"%{clean_w}%"))
                    result = await session.execute(stmt)
                    products = result.scalars().all()
                    if not products:
                        stmt_cat = select(Product).where(Product.category.ilike(f"%{clean_w}%"))
                        result_cat = await session.execute(stmt_cat)
                        products = result_cat.scalars().all()
                    found_products.extend(products)
                
                # Deduplicate products
                seen = set()
                unique_products = []
                for p in found_products:
                    if p.id not in seen:
                        seen.add(p.id)
                        unique_products.append(p)
                        
                if not unique_products:
                    return ""
                return "\n".join([
                    f"Product: {p.name}, Category: {p.category}, Price: ${p.price:.2f}, Stock: {p.stock} units."
                    for p in unique_products
                ])
                
        try:
            tool_out = await _query()
        except Exception as e:
            logger.error("Tool execution node failed: %s", e)
            
    return {"tool_output": tool_out}


# Node 3: LLM generation
async def generate_response_node(state: AgentState) -> dict:
    system_instruction = (
        "You are NexusAI Agent. Communicate in a mix of Roman Urdu and English.\n"
        "ONLY greet once. Never repeat the welcome message when a user asks about stock/products.\n"
        "Answer the user query dynamically using the context and tool output provided below (if any)."
    )
    
    prompt = f"User message: {state['message']}\n"
    if state["retrieved_context"]:
        prompt += f"\nRetrieved Semantic Context (RAG):\n{state['retrieved_context']}\n"
    if state["tool_output"]:
        prompt += f"\nReal-time Database Stock/Price Tool Output:\n{state['tool_output']}\n"
        
    response_text = await _call_llm(prompt, system_instruction, state["history"])
    return {"response": response_text}


def build_agent_graph():
    workflow = StateGraph(AgentState)
    
    workflow.add_node("retrieve_context", retrieve_context_node)
    workflow.add_node("run_tool", run_tool_node)
    workflow.add_node("generate_response", generate_response_node)
    
    workflow.set_entry_point("retrieve_context")
    
    workflow.add_edge("retrieve_context", "run_tool")
    workflow.add_edge("run_tool", "generate_response")
    workflow.add_edge("generate_response", END)
    
    return workflow.compile()


_agent_graph = build_agent_graph()


async def run_assistant_mode(db: AsyncSession, message: str, session_id: Optional[str] = None) -> QueryResponse:
    from app.database.models import ChatSession, ChatMessage
    from sqlalchemy import select
    
    history = []
    
    if session_id:
        try:
            stmt_sess = select(ChatSession).where(ChatSession.session_id == session_id)
            sess_res = await db.execute(stmt_sess)
            sess = sess_res.scalar_one_or_none()
            if not sess:
                sess = ChatSession(session_id=session_id)
                db.add(sess)
                await db.commit()
            else:
                stmt_msgs = select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.id.asc())
                msg_res = await db.execute(stmt_msgs)
                msgs = msg_res.scalars().all()
                for m in msgs[-10:]:  # Keep last 10 messages for context
                    history.append({"role": m.role, "content": m.content})
        except Exception as e:
            logger.error("Failed to load chat history: %s", e)
            
    inputs = {
        "message": message,
        "session_id": session_id,
        "history": history,
        "retrieved_context": "",
        "tool_output": "",
        "response": ""
    }
    
    answer = ""
    try:
        outputs = await _agent_graph.ainvoke(inputs)
        answer = outputs.get("response", "").strip()
    except Exception as exc:
        logger.error("LangGraph execution failed: %s", exc, exc_info=True)
        
    if not answer:
        answer = await _assistant_fallback(db, message)
        
    if session_id:
        try:
            user_msg = ChatMessage(session_id=session_id, role="user", content=message)
            asst_msg = ChatMessage(session_id=session_id, role="assistant", content=answer)
            db.add(user_msg)
            db.add(asst_msg)
            await db.commit()
        except Exception as e:
            logger.error("Failed to save chat history: %s", e)
            
    return QueryResponse(
        mode="assistant",
        answer=answer,
        row_count=0,
        meta={"engine": settings.LLM_PROVIDER, "session_id": session_id}
    )


async def run_analytics_mode(db: AsyncSession, message: str) -> QueryResponse:
    prompt = f"Admin analytics request: {message}"
    raw_sql = await _gemini_generate(prompt, _ANALYTICS_SYSTEM)
    if not raw_sql:
        raw_sql = "SELECT category, COUNT(*) AS product_count, SUM(stock) AS total_stock FROM products GROUP BY category ORDER BY product_count DESC LIMIT 20"

    raw_sql = raw_sql.replace("```sql", "").replace("```", "").strip()
    safe_sql = _guard_sql(raw_sql)

    try:
        result = await db.execute(text(safe_sql))
        rows = [_serialize_row(row) for row in result.fetchmany(100)]
    except Exception as exc:
        logger.warning("Analytics SQL execution failed: %s | SQL: %s", exc, safe_sql)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Query execution failed: {exc}",
        ) from exc

    summary = f"Analytics complete — {len(rows)} row(s) returned."
    if rows and len(rows) <= 5:
        summary += " " + json.dumps(rows, default=str)

    return QueryResponse(
        mode="analytics",
        answer=summary,
        sql_query=safe_sql,
        rows=rows,
        row_count=len(rows),
        meta={"engine": "gemini" if settings.GEMINI_API_KEY else "fallback"},
    )


async def process_ai_query(db: AsyncSession, message: str, mode: str, session_id: Optional[str] = None) -> QueryResponse:
    if mode == "analytics":
        return await run_analytics_mode(db, message)
    return await run_assistant_mode(db, message, session_id)

