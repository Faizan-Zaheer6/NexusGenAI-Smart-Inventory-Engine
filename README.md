# NexusAI: Smart Inventory Engine

Enterprise-grade async inventory & e-commerce platform built with **FastAPI**, **SQLAlchemy 2.0**, **PostgreSQL (Neon)**, **Google Gemini GenAI**, and premium **Glassmorphism UI**.

![Python](https://img.shields.io/badge/Python-3.10+-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111-green)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Neon-336791)
![Gemini](https://img.shields.io/badge/GenAI-Gemini-4285F4)

---

## Features

### Storefront
- Product search, category filters, sorting & pagination
- Real-time async cart (no page reload)
- Wishlist, flash sale countdowns, coupon checkout
- WebSocket stock update notifications (`/ws/stock`)
- **GenAI floating chatbot** (Roman Urdu + English assistant)

### TechSimPlus Dual-Mode AI Agent (`/api/v1/ai/query`)
- **Mode A — Assistant:** Customer stock & product recommendations via Gemini
- **Mode B — Analytics (Admin):** NL2SQL with strict guardrails (SELECT-only, blocks DROP/DELETE/UPDATE)
- Structured Pydantic `QueryResponse` envelope

### Admin Panel
- KPI dashboard, audit feed, multi-warehouse inventory
- Stock transfers, bulk CSV import, PDF/Excel exports
- **super_admin** RBAC for product CRUD (fixed seeder)

### Security
- JWT (HS256) + AES-256-CBC encrypted cookies
- Rate limiting, account lockout, password reset via **real SMTP** (aiosmtplib)
- No hardcoded secrets — all via environment variables

---

## Quick Start (After Laptop Restart)

### Option A — Double-click
```
run.bat
```

### Option B — PowerShell
```powershell
cd "D:\1-Work&Learnings\Projects\Inventory Manager"
.\venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open: **http://127.0.0.1:8000**

---

## First-Time Setup

```powershell
cd "D:\1-Work&Learnings\Projects\Inventory Manager"
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Edit `.env` with your values (required):
- `DATABASE_URL` — Neon PostgreSQL connection string
- `JWT_SECRET_KEY` — minimum 32 characters
- `GEMINI_API_KEY` — optional; enables full AI responses (fallback works without it)
- `SMTP_*` — optional; enables real password-reset emails

---

## Demo Credentials

| Role | Email | Password |
|------|-------|----------|
| Super Admin | `admin@nexusai.com` | `admin123` |
| Manager | `manager@nexusai.com` | `manager123` |
| Customer | `guest@nexusai.com` | `guestpassword` |

---

## Key URLs

| URL | Description |
|-----|-------------|
| `/` | Storefront + AI chatbot |
| `/admin/login` | Admin portal |
| `/admin` | Dashboard (admin required) |
| `/docs` | Swagger API docs |
| `/api/v1/ai/query` | GenAI agent endpoint |
| `/health` | Health check |

---

## Run Tests

```powershell
.\venv\Scripts\activate
pytest tests/test_endpoints.py -v
```

Covers: homepage 200, register/login tokens, cart allocation, admin route lock.

---

## Database Migrations (Alembic)

```powershell
alembic upgrade head
```

Baseline revision: `alembic/versions/0001_baseline.py`. Runtime also applies incremental DDL via `app/database/migrate.py` on startup.

---

## Vercel Deployment

```powershell
pip install mangum
vercel deploy
```

Entry point: `api/index.py` (Mangum ASGI adapter). Set all `.env` variables in Vercel project settings. Note: WebSockets and long-lived Redis connections require Vercel-compatible external services.

---

## Project Structure

```
app/
├── main.py                     # App factory, lifespan, middleware
├── core/
│   ├── config.py               # os.getenv settings (no hardcoded secrets)
│   ├── security.py             # JWT + AES-256-CBC + bcrypt
│   ├── mailer.py               # aiosmtplib async SMTP
│   ├── cache.py                # Redis + in-memory fallback
│   ├── seeder.py               # 100 products + super_admin seed
│   └── logger.py
├── database/
│   ├── models.py               # SQLAlchemy 2.0 models
│   ├── connection.py           # Async engine + get_db
│   └── migrate.py
├── services/
│   ├── ai_service.py           # Gemini dual-mode agent
│   ├── auth_service.py
│   ├── product_service.py      # N+1 batch query optimization
│   ├── order_service.py
│   └── email_service.py
├── routers/
│   ├── auth.py
│   ├── storefront.py           # Cart, WebSocket, shop
│   ├── admin.py                # super_admin product CRUD
│   └── api/v1/
│       └── ai.py               # /api/v1/ai/query
├── templates/
│   ├── store/shop.html
│   ├── admin/dashboard.html
│   └── shared/chatbot.html     # Floating GenAI widget
├── static/
tests/
├── test_endpoints.py           # pytest-asyncio + httpx
├── test_admin_login.py         # admin login specific tests
alembic/                        # Migration tracker
vercel.json
run.bat
```

---

## GenAI (Google Gemini, LangChain & LangGraph) Implementation Overview

This project implements a **Dual-Mode AI Agent** powered by **LangChain** and structured as a **LangGraph StateGraph** workflow, fully integrated with the storefront catalog and database layer.

### Features & Workflow Architecture:
1. **StateGraph Workflow (LangGraph):**
   - The chatbot query processing is structured as a stategraph (`retrieve_context` -> `run_tool` -> `generate_response` -> `END`).
   - **RAG Node (FAISS):** On server startup, a local vector database is built using **FAISS** and populated with all catalog products using Gemini Embeddings (`models/text-embedding-004`). When a product-related query is received, the RAG node executes a semantic search to fetch relevant context.
   - **Database Tool Node:** If a user specifically asks about stock status, price, or availability, the tool node queries the PostgreSQL database to get real-time price & stock.
   - **Generation Node:** Integrates memory and context to call the LLM and generate a Roman Urdu-English response.

2. **Session Chat Memory (PostgreSQL):**
   - Conversation history is saved in database tables (`chat_sessions` and `chat_messages`).
   - Guest and logged-in user chats are persisted across reloads. The chat agent retrieves the last 10 messages for context during conversation turns.

3. **Multi-LLM Provider Support:**
   - Default provider is Google Gemini, but you can configure other providers via `.env`:
     * `LLM_PROVIDER=gemini` (uses `langchain-google-genai` and Gemini)
     * `LLM_PROVIDER=groq` (uses fast Llama3 API calls via Groq)
     * `LLM_PROVIDER=ollama` (uses local offline Llama3 models via Ollama)

### GenAI Files:
* **[ai_service.py](file:///d:/1-Work&Learnings/Projects/Inventory%20Manager/app/services/ai_service.py)**: Vector DB creation, LangGraph workflow definition, nodes (RAG retriever, database inventory lookup, LLM generator), and multi-LLM API calls.
* **[ai.py (Router)](file:///d:/1-Work&Learnings/Projects/Inventory%20Manager/app/routers/api/v1/ai.py)**: Exposes the `/api/v1/ai/query` endpoint and handles permission scopes for analytics queries.
* **[ai.py (Schema)](file:///d:/1-Work&Learnings/Projects/Inventory%20Manager/app/schemas/ai.py)**: Validates input payloads (handling `session_id`, `user_message`, `mode`) and responses.
* **[chatbot.html](file:///d:/1-Work&Learnings/Projects/Inventory%20Manager/app/templates/shared/chatbot.html)**: Frontend floating chatbot widget that creates/reads session IDs in `localStorage` and submits queries.

---

## AI Agent API Example

```bash
# Customer assistant mode with memory
curl -X POST http://127.0.0.1:8000/api/v1/ai/query \
  -H "Content-Type: application/json" \
  -d '{"user_message":"Electronics mein kya available hai?","mode":"assistant","session_id":"sess_test_123"}'

# Admin analytics mode (requires admin cookie or Bearer token)
curl -X POST http://127.0.0.1:8000/api/v1/ai/query \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{"user_message":"Show total sales by category","mode":"analytics"}'
```

---

## Tech Stack

- **Backend:** FastAPI, SQLAlchemy 2.0 Async, asyncpg
- **Database:** PostgreSQL (Neon Serverless)
- **GenAI / Orchestration:** Google Gemini, LangChain, LangGraph, FAISS-cpu
- **Email:** aiosmtplib (async SMTP)
- **Auth:** Encrypted JWT cookies, refresh rotation, slowapi
- **Cache:** Redis with in-memory fallback
- **Deploy:** Vercel (Mangum)

---

## License

MIT — Portfolio / educational use.
