"""
app/database/models.py — SQLite schema DDL.

Tables:
  products              - Sainsbury's product catalogue
  stores                - Store locations and hours
  orders                - Customer orders (demo data)
  offers                - Current promotions and Nectar deals
  faqs                  - Frequently asked questions
  escalations           - Logged escalation events
  users                 - Authenticated user accounts
  conversation_sessions - Grouped voice conversation sessions per user
  conversation_messages - Individual transcript turns per session
"""

CREATE_TABLES_SQL = """
-- ── Products ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS products (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    category        TEXT NOT NULL,
    subcategory     TEXT,
    price           REAL NOT NULL,
    unit            TEXT NOT NULL DEFAULT 'each',
    description     TEXT,
    in_stock        INTEGER NOT NULL DEFAULT 1,
    stock_quantity  INTEGER DEFAULT 100,
    on_offer        INTEGER NOT NULL DEFAULT 0,
    offer_price     REAL,
    nectar_points   INTEGER DEFAULT 0,
    sku             TEXT UNIQUE,
    created_at      TEXT DEFAULT (datetime('now'))
);

-- ── Stores ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS stores (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    address         TEXT NOT NULL,
    city            TEXT NOT NULL,
    postcode        TEXT NOT NULL,
    phone           TEXT,
    email           TEXT,
    monday_hours    TEXT,
    tuesday_hours   TEXT,
    wednesday_hours TEXT,
    thursday_hours  TEXT,
    friday_hours    TEXT,
    saturday_hours  TEXT,
    sunday_hours    TEXT,
    has_cafe        INTEGER DEFAULT 0,
    has_pharmacy    INTEGER DEFAULT 0,
    has_click_collect INTEGER DEFAULT 1,
    parking_spaces  INTEGER DEFAULT 0
);

-- ── Orders ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS orders (
    id              TEXT PRIMARY KEY,
    customer_name   TEXT NOT NULL,
    customer_email  TEXT,
    status          TEXT NOT NULL DEFAULT 'processing',
    total_amount    REAL NOT NULL,
    item_count      INTEGER NOT NULL DEFAULT 1,
    store_id        TEXT REFERENCES stores(id),
    delivery_type   TEXT DEFAULT 'home_delivery',
    estimated_delivery TEXT,
    tracking_number TEXT,
    placed_at       TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
);

-- ── Offers ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS offers (
    id              TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    description     TEXT NOT NULL,
    category        TEXT,
    product_id      TEXT REFERENCES products(id),
    offer_type      TEXT NOT NULL DEFAULT 'price_cut',
    discount_pct    REAL,
    valid_from      TEXT,
    valid_until     TEXT,
    is_nectar_deal  INTEGER DEFAULT 0,
    nectar_points_bonus INTEGER DEFAULT 0
);

-- ── FAQs ────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS faqs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    question        TEXT NOT NULL,
    answer          TEXT NOT NULL,
    category        TEXT NOT NULL DEFAULT 'general',
    keywords        TEXT
);

-- ── Escalations ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS escalations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT NOT NULL,
    reason          TEXT,
    user_message    TEXT,
    status          TEXT DEFAULT 'pending',
    created_at      TEXT DEFAULT (datetime('now'))
);

-- ── Users ────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    email           TEXT NOT NULL UNIQUE,
    password_hash   TEXT NOT NULL,
    role            TEXT NOT NULL DEFAULT 'user',
    is_active       INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT DEFAULT (datetime('now')),
    last_login      TEXT
);

-- ── Conversation Sessions ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS conversation_sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title           TEXT NOT NULL DEFAULT 'Voice Conversation',
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now')),
    message_count   INTEGER NOT NULL DEFAULT 0,
    duration_seconds REAL DEFAULT 0,
    token_usage     INTEGER DEFAULT 0
);

-- ── Conversation Messages ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS conversation_messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      INTEGER NOT NULL REFERENCES conversation_sessions(id) ON DELETE CASCADE,
    role            TEXT NOT NULL,
    content         TEXT NOT NULL,
    timestamp       TEXT DEFAULT (datetime('now')),
    latency_ms      INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_conv_sessions_user ON conversation_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_conv_messages_session ON conversation_messages(session_id);
"""
