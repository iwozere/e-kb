# Personal Knowledge Base & Self-Clone — Technical Specification

> **Version:** 2.0  
> **Target deployment:** Raspberry Pi 5 (ARM64, Ubuntu 25.10)  
> **Philosophy:** Build for yourself first. Open-source second. Hosted SaaS only if there's proven demand.

---

## What This Is

A Telegram bot that acts as your **augmented memory and personal AI clone**. It does two things:

1. **Knows you** — accumulates structured knowledge about your life: notes, books, health metrics, sports, daily summaries. Searchable semantically, queryable conversationally.
2. **Writes like you** — drafts email replies in your voice, using your knowledge base as context.

The most valuable part is not the email drafting. It's the **accumulated life archive** — a year from now, you'll be able to ask "what was I thinking about in March?" or "which books shaped my view on X?" and get real answers.

---

## Stack

| Layer | Technology | Notes |
|---|---|---|
| Language | Python 3.13 | Ubuntu 25.10 default |
| Bot framework | `aiogram` 3.x | async, polling or webhook |
| Transcription | `faster-whisper` (local) | `small` model on RPi 5; fallback to OpenAI Whisper API |
| Embeddings | OpenAI Embeddings API | `text-embedding-3-small` |
| Relational DB + Vector | PostgreSQL 17 + pgvector | single store, single backup |
| AI brain | Anthropic Claude API | `claude-sonnet-4-6` |
| Scheduler | APScheduler | daily digest, weekly push |
| Config | `.env` + `config.yaml` | secrets in `.env` |
| Process manager | systemd | RPi production daemon |

### Why pgvector instead of ChromaDB

PostgreSQL is already on the RPi and must be backed up anyway. `pgvector` adds vector similarity search as a native extension — embeddings live in the same `entries` table, search is a single SQL query, and `pg_dump` covers everything. No second process, no second backup target, no sync bugs between two stores.

---

## Repository Structure

```
kb-bot/
├── bot/
│   ├── main.py                   # entry point, dispatcher + scheduler setup
│   ├── handlers/
│   │   ├── voice.py              # voice message → transcribe → classify → save
│   │   ├── text.py               # text note → classify → save
│   │   ├── search.py             # /search command
│   │   ├── ask.py                # /ask — conversational query to your clone
│   │   ├── draft.py              # /draft — email reply in your style
│   │   ├── log.py                # /log book|health|sport structured input
│   │   ├── summary.py            # /summary on-demand digest
│   │   └── admin.py              # /admin_stats
│   ├── services/
│   │   ├── transcription.py      # faster-whisper wrapper (+ Whisper API fallback)
│   │   ├── embeddings.py         # OpenAI embeddings wrapper
│   │   ├── vector_store.py       # pgvector search queries
│   │   ├── classifier.py         # auto-detect entry_type from text
│   │   ├── llm.py                # Claude API wrapper
│   │   ├── daily_digest.py       # evening pipeline: collect → summarize → save
│   │   ├── style_engine.py       # RAG + style prompt → draft reply
│   │   └── scheduler.py          # APScheduler jobs
│   ├── db/
│   │   ├── models.py             # SQLAlchemy models
│   │   ├── migrations/           # Alembic migrations
│   │   └── session.py            # async session factory
│   └── utils/
│       ├── config.py             # loads .env + config.yaml
│       └── middleware.py         # admin check middleware
├── config.yaml
├── .env
├── .env.example
├── requirements.txt
├── alembic.ini
└── deploy/
    └── kb-bot.service            # systemd unit file
```

---

## Configuration

### `config.yaml`

```yaml
admins:
  - 123456789          # Telegram user_id (integer, not string)

features:
  vector_search: true
  daily_digest: true
  weekly_digest_push: true
  max_voice_duration_sec: 300
  max_text_length_chars: 4000

digest:
  daily_time: "21:00"          # local time for evening digest
  weekly_day: "monday"
  weekly_time: "08:00"
  max_entries_per_summary: 50  # cap to avoid runaway token costs

whisper:
  use_local: true              # false = fall back to OpenAI API
  local_model: "small"         # tiny | base | small | medium
```

### `.env`

```
TELEGRAM_BOT_TOKEN=
OPENAI_API_KEY=
ANTHROPIC_API_KEY=

DATABASE_URL=postgresql+asyncpg://kbbot:password@localhost:5432/kbbot

WEBHOOK_HOST=          # leave empty for polling
WEBHOOK_PATH=/webhook

PAYMENT_SECRET=        # for HMAC token signing (future use)
```

---

## Database Schema

### PostgreSQL + pgvector

```sql
-- Enable extension (run once)
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "pgcrypto";  -- for gen_random_uuid()

-- ─────────────────────────────────────────
-- Users
-- ─────────────────────────────────────────
CREATE TABLE users (
    id            BIGINT PRIMARY KEY,   -- Telegram user_id
    username      TEXT,
    first_name    TEXT,                 -- stored for personalized messages
    created_at    TIMESTAMPTZ DEFAULT now(),
    is_active     BOOLEAN DEFAULT true
);

-- ─────────────────────────────────────────
-- User profile: style + identity
-- ─────────────────────────────────────────
CREATE TABLE user_profiles (
    user_id       BIGINT PRIMARY KEY REFERENCES users(id),
    about         TEXT,          -- who you are, what you do (plain text)
    style_prompt  TEXT,          -- your writing style description
    updated_at    TIMESTAMPTZ DEFAULT now()
);

-- ─────────────────────────────────────────
-- All entries: notes, summaries, voice logs
-- ─────────────────────────────────────────
CREATE TABLE entries (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       BIGINT REFERENCES users(id),
    text          TEXT NOT NULL,
    entry_type    TEXT NOT NULL DEFAULT 'note',
    -- 'note' | 'book' | 'health' | 'sport' | 'daily_summary' | 'weekly_summary'
    source        TEXT NOT NULL DEFAULT 'text',
    -- 'text' | 'voice' | 'system'
    title         TEXT,                -- auto-generated short label (5 words)
    duration_s    INTEGER,            -- voice duration in seconds
    embedding     vector(1536),       -- pgvector embedding
    chroma_synced BOOLEAN DEFAULT true, -- always true; legacy field, kept for compat
    created_at    TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX entries_user_created   ON entries(user_id, created_at DESC);
CREATE INDEX entries_user_type      ON entries(user_id, entry_type);
CREATE INDEX entries_embedding_hnsw ON entries
    USING hnsw (embedding vector_cosine_ops);

-- ─────────────────────────────────────────
-- Structured: books
-- ─────────────────────────────────────────
CREATE TABLE books (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     BIGINT REFERENCES users(id),
    entry_id    UUID REFERENCES entries(id) ON DELETE CASCADE,
    title       TEXT NOT NULL,
    author      TEXT,
    status      TEXT DEFAULT 'reading',   -- reading | finished | abandoned
    rating      INTEGER CHECK (rating BETWEEN 1 AND 10),
    notes       TEXT,
    date_finished DATE
);

-- ─────────────────────────────────────────
-- Structured: health metrics
-- ─────────────────────────────────────────
CREATE TABLE health_metrics (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      BIGINT REFERENCES users(id),
    entry_id     UUID REFERENCES entries(id) ON DELETE CASCADE,
    date         DATE NOT NULL DEFAULT CURRENT_DATE,
    metric_type  TEXT NOT NULL,   -- weight | sleep | blood_pressure | glucose | custom
    value        NUMERIC,
    unit         TEXT,
    notes        TEXT
);

-- ─────────────────────────────────────────
-- Structured: sport / exercise
-- ─────────────────────────────────────────
CREATE TABLE sport_logs (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      BIGINT REFERENCES users(id),
    entry_id     UUID REFERENCES entries(id) ON DELETE CASCADE,
    date         DATE NOT NULL DEFAULT CURRENT_DATE,
    activity     TEXT NOT NULL,   -- run | gym | swim | bike | yoga | custom
    duration_min INTEGER,
    intensity    TEXT,            -- low | medium | high
    distance_km  NUMERIC,
    notes        TEXT
);

-- ─────────────────────────────────────────
-- Email style examples (for /draft)
-- ─────────────────────────────────────────
CREATE TABLE email_examples (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      BIGINT REFERENCES users(id),
    incoming     TEXT NOT NULL,
    outgoing     TEXT NOT NULL,
    context      TEXT,            -- optional tag: work | personal | formal
    created_at   TIMESTAMPTZ DEFAULT now()
);
```

### Semantic Search Query

```sql
SELECT
    id,
    text,
    entry_type,
    title,
    created_at,
    1 - (embedding <=> $1::vector) AS similarity
FROM entries
WHERE user_id = $2
  AND ($3::text IS NULL OR entry_type = $3)   -- optional type filter
ORDER BY embedding <=> $1::vector
LIMIT 5;
```

---

## Core Features

### 1. Voice Note → Transcribe → Classify → Save

```
User sends voice message
    → Download OGG from Telegram
    → Transcribe via faster-whisper (local) or Whisper API (fallback)
    → classifier.py: detect entry_type from text
    → Generate title (5-word Claude summary)
    → Save to entries (PostgreSQL)
    → Generate embedding → store in entries.embedding (pgvector)
    → If type = book/health/sport → save to structured table
    → Reply: "✓ [type] saved: {title}"
```

### 2. Auto-Classification (`classifier.py`)

Claude classifies every entry before saving. This happens in a single fast call with a strict JSON response:

```python
CLASSIFY_PROMPT = """
Classify this note into exactly one type:
- note      (general thought, observation, idea)
- book      (reading, book review, learning from a book)
- health    (medical, sleep, weight, lab results, symptoms)
- sport     (workout, run, gym, physical activity)

Return only JSON: {"type": "...", "confidence": 0.0-1.0}

Note: {text}
"""
```

If confidence < 0.7, default to `"note"`.

### 3. `/ask <question>` — Query Your Clone

This is the core "clone" feature. Ask anything about yourself:

```
User: /ask what books shaped my thinking on decision-making?
    → Embed question
    → Semantic search: top 10 entries (books + notes)
    → Build prompt: system (who you are) + context (search results) + question
    → Claude answers as you, based on your data
    → Stream reply
```

**System prompt for /ask:**
```
You are an AI assistant with access to {first_name}'s personal knowledge base.
Answer questions about their life, interests, and thinking based solely on the
provided context. Be specific — reference actual entries. If the context doesn't
contain enough information, say so directly.

{about}  ← from user_profiles.about

Context (most relevant entries):
{search_results}
```

### 4. `/draft <incoming email>` — Reply in Your Style

```
User pastes incoming email text after /draft
    → Analyze email: topic, tone, sender type
    → Semantic search: relevant entries + email examples
    → Fetch style_prompt from user_profiles
    → Fetch 3 most similar email_examples
    → Build prompt: style + context + examples + incoming
    → Claude drafts reply
    → User edits and sends → optionally saves as new example (/save_example)
```

**Style engine prompt structure:**
```
You are drafting an email reply on behalf of {first_name}.

THEIR WRITING STYLE:
{style_prompt}

RELEVANT KNOWLEDGE (use if applicable):
{search_results}

EXAMPLES OF THEIR PAST REPLIES:
---
Incoming: {example_1_in}
Their reply: {example_1_out}
---
[up to 3 examples]

Now draft a reply to this incoming email:
{incoming}

Write only the reply body. Match their style exactly.
```

### 5. `/log` — Structured Input

Shorthand commands for structured data entry:

```
/log book "Antifragile" Nassim Taleb — finished — 9/10
/log health weight 78 kg
/log health sleep 7.5h
/log sport run 45min 6km high
```

The bot parses these with a small Claude call and saves to both `entries` and the relevant structured table.

### 6. `/day` — Evening Daily Digest (Manual Trigger)

```
User sends: /day
    → Fetch all entries created today (user_id, created_at::date = today)
    → If 0 entries: "Nothing logged today. Voice or type something first."
    → Send to Claude with digest prompt
    → Save result as new entry (entry_type='daily_summary', source='system')
    → Embed and store
    → Reply with the summary
```

**Daily digest prompt:**
```
Below are {first_name}'s notes from today ({date}).

Write a structured daily summary with:
1. What happened / was done (factual)
2. Patterns or observations worth noting
3. One reflection or insight

Keep it under 200 words. Use the same language as the notes.

Notes:
{entries}
```

### 7. Automated Digest Pipeline (`daily_digest.py`)

APScheduler fires at `digest.daily_time` (default 21:00):

```python
async def run_daily_digest(user_id: int):
    entries = await fetch_today_entries(user_id)
    if not entries:
        return  # no entries today, skip silently
    if len(entries) > config.digest.max_entries_per_summary:
        entries = entries[:config.digest.max_entries_per_summary]
    summary = await generate_digest(entries, user_id)
    await save_entry(user_id, summary, entry_type="daily_summary", source="system")
    await bot.send_message(user_id, f"📋 *Daily summary saved*\n\n{summary}")
```

Weekly digest fires Monday 08:00 — same logic but queries the last 7 daily summaries instead of raw entries, keeping token usage minimal.

### 8. `/search <query>` — Semantic Search

```
/search energy and focus

→ Results:
━━━━━━━━━━━━━━━━━━━━━━━━
🔍 energy and focus

1. [92%] note · May 10
   Slept 7 hours, felt sharp all morning...

2. [87%] sport · May 8
   Morning run 5km — most productive day...

3. [81%] health · May 6
   No sugar after lunch, energy stayed stable
━━━━━━━━━━━━━━━━━━━━━━━━
```

Optional type filter: `/search energy type:sport`

### 9. `/export` — Full Archive

Exports all entries as a `.md` file, grouped by date, delivered as a Telegram document. Voice entries include their auto-generated title.

---

## Bot Commands

| Command | Description |
|---|---|
| `/start` | Welcome, create user record |
| `/ask <question>` | Ask your clone anything about yourself |
| `/draft` | Paste an incoming email → get reply in your style |
| `/search <query>` | Semantic search across all entries |
| `/log book\|health\|sport ...` | Structured data entry |
| `/day` | Trigger daily digest manually |
| `/summary` | On-demand weekly digest |
| `/export` | Download full archive as Markdown |
| `/status` | Note count, streak, last entry |
| `/save_example` | Save last /draft as a style example |
| `/profile` | View/update your style_prompt and about |
| `/help` | Command list |
| `/admin_stats` | Admin only: total users, entries, disk usage |

---

## Transcription: Local-First Approach

### faster-whisper (primary)

```python
from faster_whisper import WhisperModel

model = WhisperModel("small", device="cpu", compute_type="int8")

def transcribe(audio_path: str) -> str:
    segments, _ = model.transcribe(audio_path, beam_size=5)
    return " ".join(s.text for s in segments).strip()
```

RPi 5 transcribes a 1-minute voice note in ~15–20 seconds with the `small` model. Quality is good enough for personal notes. Load the model once at startup — keep it in memory.

### Whisper API (fallback)

Set `whisper.use_local: false` in config to route through OpenAI ($0.006/min). Useful during development or if RPi is under load.

### OGG note

Telegram sends voice messages as OGG Opus. Both faster-whisper and the Whisper API accept OGG directly. `ffmpeg` and `pydub` are **not required** — remove them from dependencies.

---

## Style Profile Setup

The style profile is the heart of the clone. Set it once via `/profile`:

```
/profile style I write short, direct emails. No filler phrases.
I get to the point in the first sentence. I use lowercase for informal
messages. I rarely use exclamation marks. I sign off with just my name.

/profile about I'm a product designer based in Zurich. I work at a
B2B SaaS company. I'm interested in systems thinking, stoicism, and
long-distance running.
```

Claude uses both fields verbatim in every `/ask` and `/draft` call. Encourage the user to update this as they evolve — it's not "set and forget."

---

## Deployment: Raspberry Pi 5

### System user (security best practice)

```bash
sudo useradd --system --no-create-home --shell /usr/sbin/nologin kbbot
sudo mkdir -p /opt/kb-bot /var/lib/kb-bot
sudo chown -R kbbot:kbbot /opt/kb-bot /var/lib/kb-bot
```

### System dependencies

```bash
sudo apt update
sudo apt install python3-venv postgresql-17-pgvector
# ffmpeg is optional — only if you need audio inspection
```

### Setup

```bash
cd /opt
sudo -u kbbot git clone https://github.com/yourname/kb-bot.git
cd kb-bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# fill in .env
```

### Database

```bash
sudo -u postgres psql -c "CREATE USER kbbot WITH PASSWORD 'password';"
sudo -u postgres psql -c "CREATE DATABASE kbbot OWNER kbbot;"
sudo -u postgres psql -d kbbot -c "CREATE EXTENSION vector;"
alembic upgrade head
```

### pgvector extension install

```bash
sudo apt install postgresql-17-pgvector
```

### Systemd unit (`deploy/kb-bot.service`)

```ini
[Unit]
Description=Personal Knowledge Base Bot
After=network.target postgresql.service

[Service]
Type=simple
User=kbbot
WorkingDirectory=/opt/kb-bot
EnvironmentFile=/opt/kb-bot/.env
ExecStart=/opt/kb-bot/.venv/bin/python bot/main.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo cp deploy/kb-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable kb-bot
sudo systemctl start kb-bot
sudo journalctl -u kb-bot -f
```

### Polling vs Webhook

- **Polling** (default): zero config, works without a public domain. Recommended for personal use on RPi.
- **Webhook**: set `WEBHOOK_HOST` in `.env`. Requires public HTTPS — use nginx + Let's Encrypt or Cloudflare Tunnel.

---

## Estimated API Costs (personal use, per month)

| Operation | Estimate | Cost |
|---|---|---|
| Transcription (local faster-whisper) | ~200 voice notes | **$0.00** |
| Embeddings (200 entries + searches) | ~300k tokens | ~$0.006 |
| `/ask` and `/draft` queries (~50/month) | ~100k tokens Claude | ~$0.30 |
| Daily summaries (30×) + weekly (4×) | ~60k tokens Claude | ~$0.15 |
| **Total** | | **~$0.46/month** |

Switching to local transcription cuts the largest cost to zero. Total monthly API cost for personal use is under $1.

---

## Security Notes

- Never log full entry text or API keys.
- Run as a dedicated `kbbot` system user with no login shell.
- Admin IDs in `config.yaml` are integers (not strings) — prevents type confusion.
- Input length is capped at `config.features.max_text_length_chars` (default 4000) before any API call.
- Token budget enforced in all digest and summary calls — cap at `max_entries_per_summary` entries, never pass unbounded text to Claude.

---

## Known Issues & Decisions Made

| # | Issue | Resolution |
|---|---|---|
| 1 | Stripe renewal webhooks missing | **Removed** — no billing in v1 |
| 2 | PostgreSQL / ChromaDB desync | **Resolved** — single pgvector store, no sync needed |
| 3 | `/summary` had no token budget | **Fixed** — `max_entries_per_summary` cap in config |
| 4 | `pydub` + ffmpeg dependency | **Removed** — OGG accepted natively |
| 5 | ChromaDB collection fetched per request | **Resolved** — pgvector, no collection objects |
| 6 | No `/delete` command | **Added** — `/delete <note_id>` in command list |
| 7 | No rate limiting | **Deferred** — single personal user, not needed in v1 |
| 8 | Trial notes remaining not shown | **N/A** — no billing in v1 |
| 9 | ChromaDB vs pgvector | **pgvector chosen** — simpler ops, single backup |
| 10 | `first_name` not stored | **Fixed** — added to `users` table |
| 11 | Voice notes had no display title | **Fixed** — auto-generated 5-word title via Claude |
| 12 | Bot ran as `pi` user | **Fixed** — dedicated `kbbot` system user |
| 13 | Cost estimate was optimistic | **Recalculated** — see cost table above |
| 14 | Whisper dominates cost | **Fixed** — faster-whisper local by default |
| 15 | `user_id` exposed in payment URL | **N/A** — no billing in v1 |
| 16 | No input length limits | **Fixed** — `max_text_length_chars` in config |

---

## Roadmap

### v1 — Personal Tool (current spec)
- [x] Voice + text note capture
- [x] Auto-classification by entry type
- [x] Semantic search (pgvector)
- [x] Structured logging: books, health, sport
- [x] Daily + weekly digest pipeline
- [x] `/ask` — conversational memory queries
- [x] `/draft` — email reply in your style
- [x] Style profile setup

### v2 — Open Source Release
- [ ] Clean README with one-command setup
- [ ] Docker + docker-compose option
- [ ] Multi-user support (optional, off by default)
- [ ] Web UI for browsing entries (read-only, FastAPI + htmx)
- [ ] `/remind` — revisit a note later (APScheduler)
- [ ] Tag system: `#tag` in notes, filter in search
- [ ] Inline mode: `@botname query` from any chat

### v3 — Hosted Option (only if demand exists)
- [ ] Billing (Stripe)
- [ ] Managed cloud deployment
- [ ] Mobile-friendly web dashboard
- [ ] Import from Notion / Obsidian / Apple Notes

---

## Out of Scope (v1)

- Multi-user support and billing
- OAuth / web login
- Self-hosted LLM (swap `llm.py` to add later)
- iOS / Android app
- Automatic email sending (draft only — human reviews before sending)
