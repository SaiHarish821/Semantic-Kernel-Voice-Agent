# Architecture Deep Dive

## Component Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          BROWSER (HTML/JS)                                  │
│                                                                             │
│  ┌─────────────────┐   ┌──────────────────┐   ┌──────────────────────────┐ │
│  │  Microphone     │   │   Audio Playback  │   │  Transcript + UI         │ │
│  │  Web Audio API  │   │   AudioContext    │   │  Real-time updates       │ │
│  │  PCM16 capture  │   │   Jitter buffer   │   │  Offers, Hours sidebar   │ │
│  └────────┬────────┘   └────────▲──────────┘   └──────────────────────────┘ │
│           │ base64 PCM16        │ base64 PCM16                               │
└───────────┼─────────────────────┼────────────────────────────────────────────┘
            │ WebSocket           │ WebSocket
            │ /ws/voice           │ (audio + events)
┌───────────▼─────────────────────┴────────────────────────────────────────────┐
│                        FASTAPI SERVER (Python)                               │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │                      VoiceLiveBridge                                    │  │
│  │                                                                         │  │
│  │  Browser msgs → input_audio_buffer.append → Azure Realtime             │  │
│  │  Azure events → audio deltas              → Browser                    │  │
│  │  Azure events → function_call             → Semantic Kernel            │  │
│  │  SK result    → function_call_output      → Azure Realtime             │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │                    Semantic Kernel Orchestrator                          │ │
│  │                                                                          │ │
│  │  ProductPlugin  OrderPlugin  StorePlugin  OffersPlugin  FaqPlugin  EscPlugin │
│  │       ↓              ↓            ↓            ↓           ↓          ↓  │ │
│  │                          SQLite Database                                 │ │
│  │              (products • stores • orders • offers • faqs)               │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────────────────────┘
                      │ WebSocket (wss://)
┌──────────────────────▼───────────────────────────────────────────────────────┐
│               Azure OpenAI Realtime API                                      │
│                                                                              │
│   Input audio → Whisper STT → GPT-4o (with tools) → TTS synthesis           │
│                                                                              │
│   Server-side VAD (voice activity detection)                                 │
│   Interruption handling                                                      │
│   Turn detection (semantic VAD)                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Data Flow: Function Call

```
1. User speaks: "What milk is on offer?"
2. VAD detects end of speech
3. Whisper transcribes audio
4. GPT-4o sees transcript + tool schemas
5. GPT-4o decides to call: products-search_products(query="milk", on_offer_only=true)
6. Realtime emits: response.function_call_arguments.done
7. VoiceLiveBridge intercepts event
8. Bridge calls: invoke_plugin_function(kernel, "products", "search_products", {...})
9. ProductPlugin queries SQLite: SELECT * FROM products WHERE name LIKE '%milk%' AND on_offer=1
10. Returns: {"found":true, "products": [{"name":"Semi-Skimmed Milk","price":"£1.25","on_offer":true},...]}
11. Bridge sends: conversation.item.create (function_call_output)
12. Bridge sends: response.create (trigger new response)
13. GPT-4o synthesises: "We've got semi-skimmed milk on offer for £1.25, that's down from £1.45. Would you like to know more?"
14. TTS streams audio back through the bridge to the browser
15. Browser decodes PCM16 and plays via AudioContext
```

## Token Strategy

The system prompt is kept to **~280 tokens**. All retail data is retrieved via function calls rather than embedded context:

- ❌ Don't embed product catalogue in context
- ✅ Do call `search_products` with the user's query
- ❌ Don't embed store hours in system prompt
- ✅ Do call `get_opening_hours` per query
- ❌ Don't maintain full conversation history
- ✅ Do keep last 6 turns in rolling context

## Session Lifecycle

```
Browser connects
    ↓
VoiceSession created (UUID)
    ↓
SK Kernel built (plugins registered)
    ↓
VoiceLiveBridge instantiated
    ↓
Azure Realtime WS connected
    ↓
session.update sent (system prompt + tool schemas + VAD config)
    ↓
Bidirectional streaming begins
    │
    ├── User speaks → audio forwarded → STT → GPT-4o
    ├── GPT-4o function call → SK plugin → result → GPT-4o
    ├── GPT-4o response → TTS → audio streamed back
    └── Interruption → response.cancel → clean restart
    ↓
Client disconnects
    ↓
Bridge closed, session removed from registry
```

## Database Schema

```sql
products   (id, name, category, price, unit, on_offer, offer_price, in_stock, nectar_points)
stores     (id, name, address, city, postcode, mon-sun hours, has_cafe, has_pharmacy)
orders     (id, customer_name, status, total_amount, delivery_type, tracking_number)
offers     (id, title, description, category, offer_type, discount_pct, is_nectar_deal)
faqs       (id, question, answer, category, keywords)
escalations(id, session_id, reason, user_message, status)
```
