# Technical Specification: Personal Knowledge Base Telegram Bot

## Overview

A multi-user Telegram bot that transcribes voice messages, stores text notes, and enables semantic (vector) search over a personal knowledge base. Each user has a fully isolated data space. Admins use the bot for free; regular users must complete a payment flow before accessing features.

Deployment target: **Raspberry Pi 5** (ARM64, Debian/Ubuntu). PostgreSQL is pre-installed. ChromaDB will be installed separately.

---

## Stack

| Layer | Technology | Notes |
|---|---|---|
| Language | Python 3.11+ | |
| Bot framework | `aiogram` 3.x | async, webhook or polling |
| Transcription | OpenAI Whisper API | `whisper-1`, $0.006/min |
| Embeddings | OpenAI Embeddings API | `text-embedding-3-small`, $0.02/1M tokens |
| Relational DB | PostgreSQL (pre-installed) | notes, users, payments |
| Vector DB | ChromaDB | local persistent mode, no server needed |
| AI summaries | Anthropic Claude API | `claude-sonnet-4-20250514` |
| Payments | Stripe (recommended) or YooKassa | webhook-based confirmation |
| Config | `.env` + `config.yaml` | secrets in `.env`, admin list in `config.yaml` |
| Process manager | `systemd` | production daemon on RPi |

---

## Repository Structure

```
kb-bot/
├── bot/
│   ├── main.py               # entry point, dispatcher setup
│   ├── handlers/
│   │   ├── voice.py          # voice message handler
│   │   ├── text.py           # text note handler
│   │   ├── search.py         # /search command
│   │   ├── summary.py        # /summary command
│   │   └── payment.py        # payment flow handlers
│   ├── services/
│   │   ├── transcription.py  # Whisper API wrapper
│   │   ├── embeddings.py     # OpenAI embeddings wrapper
│   │   ├── vector_store.py   # ChromaDB operations
│   │   ├── llm.py            # Claude API wrapper
│   │   └── billing.py        # access check, payment logic
│   ├── db/
│   │   ├── models.py         # SQLAlchemy models
│   │   ├── migrations/       # Alembic migrations
│   │   └── session.py        # async session factory
│   └── utils/
│       ├── config.py         # loads .env + config.yaml
│       └── middleware.py     # access control middleware
├── config.yaml               # admin IDs, pricing, feature flags
├── .env                      # secrets (never commit)
├── .env.example
├── requirements.txt
├── alembic.ini
└── deploy/
    └── kb-bot.service        # systemd unit file
```

---

## Configuration Files

### `config.yaml`

```yaml
admins:
  - 123456789        # Telegram user_id (integer)
  - 987654321

billing:
  enabled: true
  monthly_price_usd: 5.00
  trial_notes: 10    # free notes before payment required
  payment_url: "https://your-payment-page.com"

features:
  weekly_digest: true
  vector_search: true
  max_voice_duration_sec: 300
```

### `.env`

```
TELEGRAM_BOT_TOKEN=
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=
STRIPE_PRICE_ID=

DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/kbbot
CHROMA_PERSIST_DIR=/var/lib/kb-bot/chroma

WEBHOOK_HOST=https://your-domain.com   # or leave empty for polling
WEBHOOK_PATH=/webhook
```

---

## Database Schema (PostgreSQL)

```sql
-- Users
CREATE TABLE users (
    id            BIGINT PRIMARY KEY,   -- Telegram user_id
    username      TEXT,
    created_at    TIMESTAMPTZ DEFAULT now(),
    is_active     BOOLEAN DEFAULT true
);

-- Subscription / access
CREATE TABLE subscriptions (
    id              SERIAL PRIMARY KEY,
    user_id         BIGINT REFERENCES users(id),
    status          TEXT NOT NULL,  -- 'trial' | 'active' | 'expired'
    stripe_customer_id  TEXT,
    stripe_sub_id       TEXT,
    valid_until     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- Notes
CREATE TABLE entries (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     BIGINT REFERENCES users(id),
    text        TEXT NOT NULL,
    source      TEXT NOT NULL,  -- 'voice' | 'text'
    duration_s  INTEGER,        -- for voice, seconds
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX entries_user_created ON entries(user_id, created_at DESC);
```

> ChromaDB stores embeddings separately. Each user gets their own ChromaDB collection named `user_{user_id}`. This ensures complete isolation of vector data.

---

## Access Control

### Middleware (`middleware.py`)

Every incoming update passes through `AccessMiddleware` before reaching any handler.

**Logic:**

```
1. Extract telegram_user_id from update
2. If user_id in config.admins → allow, skip all billing checks
3. Else:
   a. Load subscription from DB
   b. If status == 'active' and valid_until > now() → allow
   c. If status == 'trial' and entry_count < config.trial_notes → allow
   d. Else → block, send payment prompt
```

**Payment prompt message** (sent when access is denied):

```
Your free trial has ended (10 notes used).

To continue, subscribe for $5/month:
👉 [Pay here](https://your-payment-page.com?user_id=USER_ID&ref=SIGNED_TOKEN)

Your notes are saved and will be available after payment.
```

The `ref` parameter is an HMAC-signed token containing `user_id` so the payment page can identify the user without them needing to log in.

---

## Payment Flow

### Recommended: Stripe

**Why Stripe:** works globally, has webhooks, subscriptions, and a hosted checkout page — no need to build a payment UI.

**Flow:**

```
User hits limit
    → Bot sends message with Stripe Checkout link
    → User pays on Stripe-hosted page
    → Stripe sends webhook POST to /stripe-webhook
    → Bot backend receives webhook, verifies signature
    → Updates subscriptions table: status='active', valid_until=+30days
    → Bot sends confirmation message to user
```

**Webhook handler** (`payment.py`):

```python
@router.post("/stripe-webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig = request.headers.get("stripe-signature")
    event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        user_id = int(session["metadata"]["telegram_user_id"])
        await activate_subscription(user_id, session["subscription"])
        await bot.send_message(user_id, "Payment confirmed. Your knowledge base is active.")
```

**Checkout link generation:**

```python
session = stripe.checkout.Session.create(
    mode="subscription",
    line_items=[{"price": STRIPE_PRICE_ID, "quantity": 1}],
    success_url="https://t.me/your_bot",
    cancel_url="https://t.me/your_bot",
    metadata={"telegram_user_id": str(user_id)},
)
return session.url
```

### Alternative: YooKassa

Use if Stripe is unavailable in your region. Same webhook pattern, different SDK (`yookassa` Python package). Replace `stripe.checkout.Session` with `yookassa.Payment.create()`.

---

## Core Features

### Voice Note → Transcription → Storage

```
User sends voice message
    → Download OGG file from Telegram
    → Send to Whisper API → get transcript text
    → Save entry to PostgreSQL (entries table)
    → Generate embedding via OpenAI API
    → Store embedding in ChromaDB (collection: user_{id})
    → Reply: "Saved: {first 80 chars of transcript}..."
```

### Text Note Storage

Same as above, skip transcription step. Source = `'text'`.

### `/search <query>`

```
User sends: /search energy and focus
    → Generate embedding for query text
    → ChromaDB query: top 5 nearest in user's collection
    → Fetch full entry texts from PostgreSQL by returned IDs
    → Format and send results with similarity scores and dates
```

**Response format:**

```
Search: "energy and focus"

1. [92%] 2025-05-10
   Slept 7 hours, felt sharp all morning

2. [87%] 2025-05-08
   No sugar after lunch, energy stayed stable

3. [81%] 2025-05-06
   Morning run 5km, most productive day this week
```

### `/summary` — Weekly Digest

```
User sends: /summary
    → Fetch all entries from last 7 days for this user
    → Send to Claude API with prompt (see below)
    → Stream response back to user
```

**Claude prompt:**

```
You are a personal knowledge assistant. Below are notes taken by the user over the past week.

Produce a structured digest with:
1. Main themes (2-4 sentences)
2. Recurring patterns or observations
3. One actionable insight based on the notes

Notes:
{entries}

Be concise. Use the same language as the notes.
```

### `/export`

Export all user entries as a `.md` file, formatted chronologically. Delivered as a Telegram document.

---

## Bot Commands

| Command | Access | Description |
|---|---|---|
| `/start` | all | Welcome message, create user record |
| `/search <query>` | paid/admin | Semantic search |
| `/summary` | paid/admin | Weekly AI digest |
| `/export` | paid/admin | Download all notes as Markdown |
| `/status` | all | Show subscription status and note count |
| `/help` | all | Command list |
| `/admin_stats` | admin only | Total users, active subs, note count |

---

## ChromaDB Setup on Raspberry Pi 5

```bash
pip install chromadb
```

ChromaDB runs in **local persistent mode** — no server process needed:

```python
import chromadb

client = chromadb.PersistentClient(path="/var/lib/kb-bot/chroma")

def get_user_collection(user_id: int):
    return client.get_or_create_collection(
        name=f"user_{user_id}",
        metadata={"hnsw:space": "cosine"}
    )
```

Data is stored on disk at `CHROMA_PERSIST_DIR`. No additional services to manage.

---

## Deployment: Raspberry Pi 5

### System dependencies

```bash
sudo apt update
sudo apt install python3.11 python3.11-venv python3-pip ffmpeg
```

`ffmpeg` is required by the `pydub` library to convert Telegram's OGG voice files before sending to Whisper.

### Setup

```bash
cd /opt
sudo git clone https://github.com/yourname/kb-bot.git
cd kb-bot
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

sudo mkdir -p /var/lib/kb-bot/chroma
sudo chown -R pi:pi /var/lib/kb-bot

cp .env.example .env
# fill in .env with your keys
```

### Run database migrations

```bash
alembic upgrade head
```

### Systemd unit (`deploy/kb-bot.service`)

```ini
[Unit]
Description=Knowledge Base Telegram Bot
After=network.target postgresql.service

[Service]
Type=simple
User=pi
WorkingDirectory=/opt/kb-bot
EnvironmentFile=/opt/kb-bot/.env
ExecStart=/opt/kb-bot/venv/bin/python bot/main.py
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
sudo journalctl -u kb-bot -f   # follow logs
```

### Polling vs Webhook

- **Polling** (default): simpler, works without a public domain, fine for low traffic. Set `WEBHOOK_HOST=` empty.
- **Webhook**: requires a public HTTPS URL pointing to the RPi. Use `ngrok` for local testing or a reverse proxy (nginx + Let's Encrypt) for production.

---

## Estimated API Costs (per active user/month)

| Operation | Estimate | Cost |
|---|---|---|
| ~200 voice notes/month, avg 1 min | 200 min × $0.006 | $1.20 |
| Embeddings for 200 notes + searches | ~300k tokens × $0.02/1M | $0.006 |
| 4 weekly summaries via Claude | ~8k tokens × Claude pricing | ~$0.05 |
| **Total per user** | | **~$1.30** |

At $5/month subscription price, margin per paying user is ~$3.70 before infrastructure.

---

## Security Notes

- Never log full note content or API keys.
- Stripe webhook must verify signature on every request (`stripe.Webhook.construct_event`).
- The `ref` token in payment URLs must be HMAC-signed with a secret to prevent user_id spoofing.
- ChromaDB collections are named by `user_id` — queries always filter by collection, ensuring no cross-user data leakage.
- Admin IDs in `config.yaml` are integers (not strings) to prevent type confusion bugs.

---

## Out of Scope (v1)

- Web dashboard
- OAuth login
- Multi-language UI (bot language follows user's note language automatically via Claude)
- Self-hosted LLM (can be added later by swapping `llm.py`)

---

## Review: Issues, Ideas & Proposed Improvements

> Added 2026-05-15. These are design-level observations — not all are blockers, but each is worth a decision before coding starts.

---

### Bugs / Correctness Issues

**1. Stripe subscription renewals are not handled.**
The webhook handler only processes `checkout.session.completed` (first payment). Monthly renewals emit `invoice.payment_succeeded`. Without handling it, subscriptions will expire after 30 days even for paying users. Add:

```python
if event["type"] in ("checkout.session.completed", "invoice.payment_succeeded"):
    ...  # same activation logic, update valid_until = now() + 30 days
```

**2. PostgreSQL and ChromaDB can silently desync.**
If the bot crashes between saving a note to PostgreSQL and storing its embedding in ChromaDB, the note exists in one but not the other. A search will miss it; a delete would leave orphaned vectors. Fix: store a `chroma_synced: bool` flag on `entries`, and run a startup reconciliation job that re-embeds unsynced entries.

**3. `/summary` has no token budget.**
If a user has 200 notes in 7 days, the prompt sent to Claude could easily exceed practical context limits and cost far more than the $0.05 estimate. Cap at the most recent N entries or ~8k characters of text, and tell the user if entries were truncated.

**4. `pydub` + ffmpeg may be unnecessary.**
The Whisper API accepts `.ogg` files directly (Telegram voice messages are OGG Opus). Verify whether conversion is actually needed before adding the ffmpeg system dependency. If it is needed (e.g. for duration detection), note that `ffprobe` can be used standalone without `pydub`.

**5. `get_or_create_collection` is called per request.**
Creating/fetching a ChromaDB collection on every voice or text message adds latency. Cache the collection object in a module-level dict keyed by `user_id`. Collections don't need to be recreated once the client is alive.

---

### Missing Features (worth adding to v1)

**6. `/delete <note_id>` command.**
Users will inevitably want to remove a note (misfire, private content). Without this, the only option is to delete the whole account. The ID can be shown in search results.

**7. Rate limiting.**
A single user sending 50 voice messages in an hour would cost ~$0.30 in Whisper alone — not catastrophic, but worth guarding. A simple per-user counter in Redis or even in-memory (acceptable for single-process RPi deployment) with a sliding window (e.g., 20 voice notes/hour) prevents accidental cost spikes.

**8. `/status` should show trial notes remaining.**
Currently the spec says `/status` shows "subscription status and note count" but doesn't specify whether it tells trial users how many free notes they have left. This is important UX — users should know they're at 7/10 before hitting the wall.

---

### Architecture Suggestions

**9. Consider replacing ChromaDB with pgvector.**
PostgreSQL is already on the RPi and must be backed up anyway. Adding the `pgvector` extension (`sudo apt install postgresql-16-pgvector`) eliminates ChromaDB entirely: embeddings live in a `entries.embedding vector(1536)` column, search is `ORDER BY embedding <=> query_vec LIMIT 5`, and backups are a single `pg_dump`. The tradeoff is that pgvector's HNSW index requires PostgreSQL 15+ and explicit `CREATE INDEX USING hnsw`. For the scale of this project (one RPi, dozens of users), pgvector is simpler and more reliable.

Revised `entries` table with pgvector:
```sql
ALTER TABLE entries ADD COLUMN embedding vector(1536);
CREATE INDEX entries_embedding_hnsw ON entries USING hnsw (embedding vector_cosine_ops);
```

Search query:
```sql
SELECT id, text, created_at,
       1 - (embedding <=> $1) AS similarity
FROM entries
WHERE user_id = $2
ORDER BY embedding <=> $1
LIMIT 5;
```

**10. Add a `first_name` column to `users`.**
Telegram provides `first_name` in every update. Storing it enables personalized messages ("Good summary, Alex!") without extra API calls.

**11. Add a `display_name` to `entries` for voice notes.**
Transcripts are stored as raw text. A short auto-generated title (first sentence, or Claude-generated 5-word label) makes `/export` and future search UX much friendlier.

**12. Dedicated service user instead of `pi`.**
The systemd unit runs as `pi` (the default RPi admin user). Best practice is a dedicated `kbbot` system user with no login shell and access only to `/opt/kb-bot` and `/var/lib/kb-bot`. This limits blast radius if the bot process is compromised.

```bash
sudo useradd --system --no-create-home --shell /usr/sbin/nologin kbbot
sudo chown -R kbbot:kbbot /opt/kb-bot /var/lib/kb-bot
```

---

### Cost Model Observations

**13. The cost estimate is optimistic.**
The "$0.05 for 4 weekly summaries" line assumes ~8k tokens total across all 4 summaries. At ~2k tokens per summary (input + output), Claude Sonnet pricing puts this closer to $0.10–$0.15. Still well within the $3.70 margin, but worth calibrating. More importantly, the cost model doesn't account for search queries — each `/search` call generates an embedding (~$0.000004) which is negligible, but worth noting.

**14. Voice transcription is the dominant cost.**
At $1.20/user/month for transcription vs ~$0.06 for everything else, Whisper is 95% of the cost. If the RPi ever has spare CPU cycles, a local Whisper model (`faster-whisper` with the `base` or `small` model) would cut costs to near zero at the expense of slightly lower quality. Worth flagging as a near-term option in the "Out of Scope" section.

---

### Security Gaps

**15. The payment URL reveals `user_id` in plaintext.**
The spec says the `ref` token is HMAC-signed, but also shows `?user_id=USER_ID&ref=SIGNED_TOKEN`. The `user_id` should be inside the signed token, not separate — otherwise a user can observe any other user's `user_id` from their own URL and probe the system. Embed `user_id` inside the token payload only:

```python
import hmac, hashlib, json, base64, time

def make_payment_token(user_id: int, secret: str) -> str:
    payload = json.dumps({"uid": user_id, "exp": int(time.time()) + 3600})
    payload_b64 = base64.urlsafe_b64encode(payload.encode()).decode()
    sig = hmac.new(secret.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{sig}"
```

**16. No mention of input length limits.**
A text note with 100k characters would be expensive to embed and summarize. Cap text input at a reasonable limit (e.g., 4000 characters for text notes, and rely on Telegram's voice duration limit config for voice).

---

### Nice-to-Have Ideas (post-v1)

- **`/remind` command** — set a reminder to revisit a specific note. Trivial to implement with `APScheduler`.
- **Tag system** — users prefix notes with `#tag` and can filter search by tag. Tags are extracted by the bot before saving.
- **Inline mode** — `@botname query` lets users search their KB from any Telegram chat without opening the bot directly.
- **Weekly digest push** — instead of requiring `/summary`, the bot sends the digest automatically every Monday morning. Uses `APScheduler` or a systemd timer.
- **Note deduplication** — before saving, check cosine similarity against recent embeddings; if >0.95, warn the user "This looks similar to a note from 3 days ago."
