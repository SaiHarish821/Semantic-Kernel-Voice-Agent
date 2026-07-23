# Sainsbury's AI Voice Agent

A production-ready, real-time AI voice assistant for Sainsbury's retail operations, built with **Azure OpenAI Realtime (GPT-4o)**, **Semantic Kernel**, **FastAPI**, and a modern glassmorphism dark-mode UI.

---

## Quick Start

### 1. Prerequisites

| Tool | Min version |
|------|------------|
| Python | 3.11+ |
| pip | 24+ |
| Azure OpenAI | Resource with GPT-4o-realtime-preview deployment |

> An Azure OpenAI resource with access to `gpt-4o-realtime-preview` is required. Enable it in [Azure AI Foundry](https://ai.azure.com).

> **Multiple Python versions?** If you have multiple Python versions installed, ensure you use Python 3.11 explicitly. On Windows with `py` launcher: use `py -3.11` instead of `python`.

---

### 2. Clone / open the project

The project lives in `c:\Projects\Semantic Kernel\`.

---

### 3. Install dependencies

```powershell
cd "c:\Projects\Semantic Kernel"

# Using Python 3.11 explicitly (recommended if multiple versions installed)
py -3.11 -m pip install -r requirements.txt

# Or if python == 3.11
pip install -r requirements.txt
```

---

### 4. Configure environment

```powershell
Copy-Item .env.example .env
```

Edit `.env` and fill in your Azure OpenAI credentials:

```env
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your-key-here
AZURE_OPENAI_REALTIME_DEPLOYMENT=gpt-realtime
AZURE_OPENAI_CHAT_DEPLOYMENT=gpt-4o
```

---

### 5. Run the server

```powershell
# Using Python 3.11
py -3.11 run.py

# Or if python == 3.11
python run.py
```

Open **http://localhost:8000** in your browser.

---

## Architecture

```
Browser ──────────────────── FastAPI WebSocket (/ws/voice)
  │  audio_chunk (base64 PCM16)      │
  │  transcript, audio               │
  │◄─────────────────────────────────┤
                              VoiceLiveBridge
                                     │  Raw audio forwarded
                                     ▼
                         Azure OpenAI Realtime WS
                         (STT + GPT-4o + TTS in one WS)
                                     │  function_call events
                                     ▼
                         Semantic Kernel Orchestrator
                                     │  @kernel_function calls
                         ┌───────────┼───────────────────┐
                         ▼           ▼                   ▼
                    ProductPlugin  OrderPlugin       StorePlugin
                    OffersPlugin   FaqPlugin     EscalationPlugin
                                     │
                                  SQLite DB
                         (products, orders, offers, FAQs)
```

---

## Plugins

| Plugin | Functions | Use cases |
|--------|-----------|-----------|
| `ProductPlugin` | `search_products`, `get_product_details`, `check_stock` | "Do you have oat milk?" |
| `OrderPlugin` | `get_order_status`, `track_delivery`, `initiate_return` | "Where's my order ORD-2024-88322?" |
| `StorePlugin` | `get_store_info`, `get_opening_hours`, `find_nearest_store` | "What time do you close on Sunday?" |
| `OffersPlugin` | `get_current_offers`, `get_nectar_deals`, `get_category_deals` | "Any deals on frozen food?" |
| `FaqPlugin` | `answer_faq`, `get_return_policy`, `get_delivery_policy` | "How do I return an item?" |
| `EscalationPlugin` | `escalate_to_human`, `log_complaint`, `send_callback_request` | "I need to speak to someone" |

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Serves the UI |
| `GET` | `/health` | Liveness + readiness check |
| `WS` | `/ws/voice` | Real-time voice session |
| `GET` | `/api/v1/products` | Product search (`?q=milk&category=Dairy&on_offer=true`) |
| `GET` | `/api/v1/offers` | Active offers (`?category=Dairy&nectar_only=false`) |
| `GET` | `/api/v1/stores` | Store list (`?city=London`) |
| `GET` | `/api/v1/sessions` | Active session stats |
| `GET` | `/docs` | Swagger UI (development only) |

---

## Project Structure

```
sainsburys-voice-agent/
├── .env.example          # Environment template
├── .env                  # Your credentials (gitignored)
├── requirements.txt
├── run.py                # Entry point
├── app/
│   ├── config.py         # Pydantic Settings
│   ├── main.py           # FastAPI app
│   ├── logging_config.py # Structured JSON logging
│   ├── api/
│   │   ├── routes.py     # HTTP routes
│   │   └── websocket.py  # WS session handler
│   ├── voice/
│   │   ├── bridge.py     # Realtime API ↔ Browser proxy
│   │   └── session_manager.py
│   ├── agent/
│   │   ├── kernel_factory.py  # SK kernel + plugins
│   │   └── system_prompt.py
│   ├── plugins/          # 6 SK plugin classes
│   ├── database/
│   │   ├── connection.py
│   │   ├── models.py     # DDL
│   │   └── seed.py       # 45 products, 5 stores, 10 orders…
│   └── static/           # index.html, style.css, app.js
└── docs/
    ├── architecture.md
    └── deployment.md
```

---

## Sample Queries to Try

```
"What milk do you have on offer?"
"Check order ORD-2024-88322"
"What are your opening hours on Sunday?"
"Do you have any Nectar deals this week?"
"How do I return an item without a receipt?"
"Is the sourdough bread in stock?"
"Find me a store in Manchester"
"I'd like to make a complaint"
"What time does the Clapham store close?"
"Tell me about the weather"  → polite refusal
```

---

## Configuration Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `AZURE_OPENAI_ENDPOINT` | — | Required. Your Azure OpenAI endpoint |
| `AZURE_OPENAI_API_KEY` | — | Required. API key |
| `AZURE_OPENAI_REALTIME_DEPLOYMENT` | `gpt-4o-realtime-preview` | Realtime model deployment name |
| `AZURE_OPENAI_CHAT_DEPLOYMENT` | `gpt-4o` | Chat model for SK |
| `AZURE_OPENAI_API_VERSION` | `2024-10-01-preview` | API version |
| `VOICE_NAME` | `alloy` | TTS voice: `alloy`, `echo`, `fable`, `onyx`, `nova`, `shimmer` |
| `DATABASE_PATH` | `./data/sainsburys.db` | SQLite file path |
| `APP_ENV` | `development` | `development` or `production` |
| `APP_PORT` | `8000` | HTTP port |
| `MAX_CONTEXT_TURNS` | `6` | Rolling conversation window |

---

## Health Check

```bash
curl http://localhost:8000/health
```

Expected response:
```json
{
  "status": "healthy",
  "checks": {
    "database": { "status": "ok", "products": 45 },
    "config": { "status": "ok", "endpoint_configured": true, "key_configured": true },
    "sessions": { "active": 0 },
    "uptime_seconds": 42.1
  }
}
```

---

## Extending the Agent

### Add a new plugin

1. Create `app/plugins/my_plugin.py`:
   ```python
   from semantic_kernel.functions import kernel_function

   class MyPlugin:
       @kernel_function(description="What this does")
       async def my_function(self, query: str) -> str:
           return '{"result": "..."}' 
   ```

2. Register in `app/agent/kernel_factory.py`:
   ```python
   from app.plugins.my_plugin import MyPlugin
   kernel.add_plugin(MyPlugin(), plugin_name="my_plugin")
   ```

That's it — the tool definition is auto-exported and the realtime session picks it up.

### Change the agent voice

Set `VOICE_NAME=nova` (or `alloy`, `echo`, `fable`, `onyx`, `shimmer`) in `.env`.

### Add more products / FAQs

Edit the `PRODUCTS` / `FAQS` lists in `app/database/seed.py`. Delete `data/sainsburys.db` and restart to reseed.
