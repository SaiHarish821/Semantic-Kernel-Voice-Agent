# Sainsbury's AI Voice Agent 🎙️🛒

A production-ready, real-time AI voice assistant for Sainsbury's retail operations, built with **Azure OpenAI Realtime (GPT-4o)**, **Semantic Kernel**, **FastAPI**, and a modern glassmorphism dark-mode UI.

Repository: [https://github.com/SaiHarish821/Semantic-Kernel-Voice-Agent](https://github.com/SaiHarish821/Semantic-Kernel-Voice-Agent)

---

## ⚡ Quick Start

### 1. Prerequisites

| Tool | Min Version | Description |
|------|-------------|-------------|
| **Python** | `3.11+` | Primary runtime environment |
| **pip** | `24+` | Package installer |
| **Azure OpenAI** | `gpt-realtime` & `gpt-5` | Deployment with Realtime WebSockets support |

> An Azure OpenAI resource with access to `gpt-realtime` is required. Enable it in [Azure AI Foundry](https://ai.azure.com).

> **Multiple Python versions?** If you have multiple Python versions installed, ensure you use Python 3.11 explicitly. On Windows with `py` launcher: use `py -3.11` instead of `python`.

---

### 2. Clone the Repository

```powershell
git clone https://github.com/SaiHarish821/Semantic-Kernel-Voice-Agent.git
cd Semantic-Kernel-Voice-Agent
```

---

### 3. Install Dependencies

```powershell
# Create virtual environment (optional but recommended)
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install requirements
pip install -r requirements.txt
```

---

### 4. Configure Environment

Copy `.env.example` to `.env`:

```powershell
Copy-Item .env.example .env
```

Edit `.env` and fill in your Azure OpenAI credentials:

```env
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your-azure-api-key-here
AZURE_OPENAI_REALTIME_DEPLOYMENT=gpt-realtime
AZURE_OPENAI_API_VERSION=2025-04-01-preview
AZURE_OPENAI_CHAT_DEPLOYMENT=gpt-5
```

---

### 5. Run the Server

```powershell
python run.py
```

Open **`http://localhost:8000`** in your browser.

---

## 🏗️ Architecture

```
Browser (Web Audio API) ───────────── FastAPI WebSocket (/ws/voice)
   │  audio_chunk (base64 PCM16)          │
   │  transcript, audio                   │
   │◄─────────────────────────────────────┤
                                   VoiceLiveBridge
                                          │  Forward PCM16 audio
                                          ▼
                              Azure OpenAI Realtime WS
                              (STT + GPT-4o + TTS via WSS)
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

## 🧩 Plugins & Capabilities

| Plugin | Functions | Use Cases |
|--------|-----------|-----------|
| **`ProductPlugin`** | `search_products`, `get_product_details`, `check_stock` | *"Do you have oat milk in stock?"* |
| **`OrderPlugin`** | `get_order_status`, `track_delivery`, `initiate_return` | *"Where's my order ORD-2024-88322?"* |
| **`StorePlugin`** | `get_store_info`, `get_opening_hours`, `find_nearest_store` | *"What time does the Clapham store close on Sunday?"* |
| **`OffersPlugin`** | `get_current_offers`, `get_nectar_deals`, `get_category_deals` | *"Any Nectar deals on bakery items?"* |
| **`FaqPlugin`** | `answer_faq`, `get_return_policy`, `get_delivery_policy` | *"How do I return an item without a receipt?"* |
| **`EscalationPlugin`** | `escalate_to_human`, `log_complaint`, `send_callback_request` | *"I'd like to speak to a customer service supervisor"* |

---

## 📡 API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Web Voice Assistant Dashboard UI |
| `GET` | `/health` | Liveness & database readiness check |
| `WS` | `/ws/voice` | Real-time audio streaming WebSocket |
| `GET` | `/api/v1/products` | Search product catalog |
| `GET` | `/api/v1/offers` | View active discounts & Nectar prices |
| `GET` | `/api/v1/stores` | Find stores & opening hours |
| `GET` | `/api/v1/sessions` | Monitor active voice sessions |
| `GET` | `/docs` | OpenAPI / Swagger documentation |

---

## 📁 Project Structure

```
Semantic-Kernel-Voice-Agent/
├── .env.example          # Environment variables template
├── .gitignore            # Excludes secrets, venv, and database files
├── requirements.txt      # Python package dependencies
├── run.py                # Server entry point
├── app/
│   ├── config.py         # Pydantic settings & WebSocket URL generation
│   ├── main.py           # FastAPI application setup & CORS
│   ├── logging_config.py # Structured JSON logger
│   ├── api/
│   │   ├── routes.py     # REST endpoints
│   │   └── websocket.py  # WebSocket connection handler
│   ├── voice/
│   │   ├── bridge.py     # Realtime API ↔ Browser audio proxy
│   │   └── session_manager.py # Session state manager
│   ├── agent/
│   │   ├── kernel_factory.py  # SK Kernel setup & tool exporter
│   │   └── system_prompt.py   # Sainsbury's persona prompt
│   ├── plugins/          # 6 Semantic Kernel plugin modules
│   ├── database/
│   │   ├── connection.py
│   │   ├── models.py     # SQLite table definitions
│   │   └── seed.py       # Seed data generator (products, stores, orders)
│   └── static/           # HTML5 / Glassmorphism CSS / JS Web Audio UI
└── docs/
    ├── architecture.md   # Architectural design details
    └── deployment.md     # Production deployment instructions
```

---

## 🗣️ Sample Voice Queries

- *"What milk do you have on offer right now?"*
- *"Check status for order ORD-2024-88322."*
- *"What are the Sunday opening hours for the Manchester store?"*
- *"Do you have any Nectar deals on fresh produce?"*
- *"How can I request a refund for damaged goods?"*
- *"Is organic sourdough bread available?"*
- *"I need to register a complaint about a delivery."*

---

## ⚙️ Configuration Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `AZURE_OPENAI_ENDPOINT` | — | Base URL of your Azure OpenAI resource |
| `AZURE_OPENAI_API_KEY` | — | API key for authentication |
| `AZURE_OPENAI_REALTIME_DEPLOYMENT` | `gpt-realtime` | Deployment name for Realtime model |
| `AZURE_OPENAI_API_VERSION` | `2025-04-01-preview` | Realtime API protocol version |
| `AZURE_OPENAI_CHAT_DEPLOYMENT` | `gpt-5` | Chat deployment for SK orchestrator |
| `VOICE_NAME` | `alloy` | TTS voice (`alloy`, `echo`, `fable`, `onyx`, `nova`, `shimmer`) |
| `DATABASE_PATH` | `./data/sainsburys.db` | SQLite database file location |
| `APP_PORT` | `8000` | Local server port |

---

## 🏥 Health Check

Test system health and database readiness:

```bash
curl http://localhost:8000/health
```

Sample Output:
```json
{
  "status": "healthy",
  "checks": {
    "database": { "status": "ok", "products": 45 },
    "config": { "status": "ok", "endpoint_configured": true, "key_configured": true },
    "sessions": { "active": 0 },
    "uptime_seconds": 12.4
  }
}
```

---

## 🛠️ Extending the Agent

### Adding a New Plugin

1. Create a new plugin file in `app/plugins/my_plugin.py`:
   ```python
   from semantic_kernel.functions import kernel_function

   class MyPlugin:
       @kernel_function(description="Description of what this plugin function does")
       async def my_function(self, argument: str) -> str:
           return '{"result": "success"}'
   ```

2. Register the plugin in `app/agent/kernel_factory.py`:
   ```python
   from app.plugins.my_plugin import MyPlugin
   
   kernel.add_plugin(MyPlugin(), plugin_name="my_plugin")
   ```

The tool definition is automatically exported and registered with the Azure OpenAI Realtime session.

---

## 📄 License

Distributed under the MIT License. See `LICENSE` for details.
