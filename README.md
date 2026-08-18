# KB Bot — Personal Knowledge Base & AI Clone

A personal-use Telegram bot that captures voice notes and text, auto-classifies them,
and lets you query your own knowledge base through an AI "clone" of yourself.
Designed to run on a **Raspberry Pi 5** (Ubuntu 25.10) — no cloud servers required.

---

## Features

| Area | What it does |
|---|---|
| 🎙 **Voice capture** | Transcribes voice messages (local faster-whisper or OpenAI Whisper API) |
| 📝 **Text notes** | Saves any plain text message as a note |
| 🗂 **Auto-classification** | Claude tags each entry: `note`, `book`, `health`, or `sport` |
| 🏷 **Auto-title** | 5-word title generated for every entry |
| 🔍 **Semantic search** | `/search` — vector similarity via pgvector |
| 🤖 **AI Q&A** | `/ask` — multi-turn conversation grounded in your notes |
| ✉️ **Email drafting** | `/draft` — reply in your own writing style |
| 📋 **Daily digest** | `/day` — AI summary of today's entries (also scheduled 21:00) |
| 📊 **Weekly digest** | `/summary` — weekly reflection (also scheduled Mon 08:00) |
| 📚 **Structured logs** | `/log` — track books, health metrics, sport sessions |
| 👤 **Profile** | `/profile` — set your about & email style for the AI clone |
| 📦 **Export** | `/export` — all notes as a Markdown file |
| 🗑 **Safe delete** | `/delete` — preview + confirm before permanent removal |
| 🔥 **Streak** | `/status` — consecutive active days, SQL islands-and-gaps |

---

## Bot Commands

### Capture

| Command | Description |
|---|---|
| _(voice message)_ | Transcribed, classified, titled, and saved automatically |
| _(text message)_ | Saved as a note |
| `/log book <text>` | Log a book (title, author, status, rating) |
| `/log health <text>` | Log a health metric (weight, BP, sleep, …) |
| `/log sport <text>` | Log a sport session (activity, duration, intensity) |

### Query

| Command | Description |
|---|---|
| `/ask <question>` | Ask your AI clone anything; keeps 5-turn context for 15 min |
| `/search <query>` | Semantic search. Add `type:book` / `type:sport` etc. to filter |
| `/day` | Generate (and save) a digest of today's entries |
| `/summary` | Generate (and save) a weekly reflection from the last 7 daily digests |

### Email drafting

| Command | Description |
|---|---|
| `/draft <incoming email>` | Draft a reply in your style. Inline buttons: ✅ Save as Example · 🔄 Regenerate |
| `/profile` | Show current `about` and `style` prompt |
| `/profile about <text>` | Update the "who you are" context used by `/ask` and `/draft` |
| `/profile style <text>` | Update the writing-style description used by `/draft` |

### Other

| Command | Description |
|---|---|
| `/status` | Total notes, last entry timestamp, streak |
| `/export` | Download all notes as a `.md` file |
| `/delete <id>` | Delete entry — shows preview and confirm button. IDs come from `/search` |
| `/start` / `/help` | Welcome message and full command list |
| `/admin_stats` | _(admin only)_ Users, entries by type, DB table sizes |

---

## Stack

| Layer | Technology |
|---|---|
| Language | Python 3.14 |
| Bot framework | aiogram 3.x (async) |
| AI brain | Anthropic Claude (`claude-sonnet-4-6`) + prompt caching |
| Transcription | faster-whisper (local, CPU, int8) · OpenAI Whisper API (fallback) |
| Embeddings | OpenAI `text-embedding-3-small` |
| Vector search | pgvector (PostgreSQL extension) · HNSW index |
| Relational DB | PostgreSQL 17 |
| Scheduler | APScheduler (`AsyncIOScheduler`) |
| Process manager | systemd |

---

## Project Structure

```
e-kb/
├── bot/
│   ├── main.py                    # entry point — dispatcher, scheduler, polling/webhook
│   ├── handlers/
│   │   ├── start.py               # /start /help /status
│   │   ├── ask.py                 # /ask (multi-turn Q&A)
│   │   ├── draft.py               # /draft + save/regen callbacks
│   │   ├── log.py                 # /log book|health|sport
│   │   ├── summary.py             # /day /summary
│   │   ├── search.py              # /search
│   │   ├── delete.py              # /delete + confirm callback
│   │   ├── profile.py             # /profile
│   │   ├── export.py              # /export
│   │   ├── admin.py               # /admin_stats
│   │   ├── voice.py               # voice message handler
│   │   └── text_note.py           # plain text (catch-all)
│   ├── services/
│   │   ├── llm.py                 # Claude API wrapper (complete / complete_with_history)
│   │   ├── entry_service.py       # shared pipeline: classify → title → embed → save
│   │   ├── classifier.py          # classify_entry / generate_title / extract_structured
│   │   ├── transcription.py       # faster-whisper (local) or Whisper API
│   │   ├── embeddings.py          # OpenAI text-embedding-3-small
│   │   ├── vector_store.py        # search_similar / fetch_today_entries / fetch_recent_summaries
│   │   ├── conversation.py        # in-memory 5-turn history, 15-min expiry
│   │   ├── daily_digest.py        # daily/weekly summary generators + APScheduler targets
│   │   ├── style_engine.py        # /draft pipeline
│   │   ├── scheduler.py           # APScheduler setup/start/stop
│   │   └── users.py               # get_or_create_user
│   ├── db/
│   │   ├── models.py              # SQLAlchemy ORM models
│   │   ├── session.py             # AsyncSessionLocal factory
│   │   └── migrations/            # Alembic versions
│   └── utils/
│       ├── config.py              # Pydantic settings (config.yaml + .env)
│       └── middleware.py          # AccessMiddleware (auth + user upsert)
├── config.yaml                    # admin IDs, feature flags, digest times, whisper config
├── .env                           # secrets (never commit)
├── .env.example
├── requirements.txt
├── alembic.ini
└── deploy/
    └── kb-bot.service             # systemd unit
```

---

## Setup

### 1. System dependencies (Ubuntu 25.10)

```bash
sudo apt update
sudo apt install python3-venv ffmpeg postgresql-17-pgvector
```

If `postgresql-17-pgvector` is not in the repo, build from source:

```bash
sudo apt install postgresql-server-dev-17 build-essential git
git clone --branch v0.8.0 https://github.com/pgvector/pgvector.git
cd pgvector && make && sudo make install
```

### 2. Database

```bash
sudo -u postgres createdb kbbot
sudo -u postgres psql -c "CREATE USER kbbot WITH PASSWORD 'changeme';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE kbbot TO kbbot;"
```

### 3. Project

```bash
git clone git@github.com:youruser/e-kb.git
cd e-kb
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Local (on-device) Whisper transcription is a separate, optional install — its backend
(`ctranslate2`) doesn't ship Python 3.14 wheels yet. Add it on top only if your
interpreter is supported:

```bash
pip install -r requirements-local-whisper.txt
```

Without it, `whisper.use_local: true` in `config.yaml` still works — it logs a
warning and falls back to the OpenAI Whisper API automatically.

### 4. Configuration

```bash
cp .env.example .env
nano .env
```

Required values in `.env`:

```
TELEGRAM_BOT_TOKEN=       # from @BotFather
OPENAI_API_KEY=           # for Whisper API fallback + embeddings
ANTHROPIC_API_KEY=        # for Claude (classification, /ask, /draft, digests)
DATABASE_URL=postgresql+asyncpg://kbbot:changeme@localhost:5432/kbbot
```

Optional (webhook mode):

```
WEBHOOK_HOST=https://your-pi.example.com
WEBHOOK_PATH=/webhook
WEB_PORT=8080
```

`config.yaml` is per-deployment (admin IDs, feature flags) and gitignored, so `git pull`
never collides with your live settings. Copy the template and edit it:

```bash
cp config.yaml.example config.yaml
nano config.yaml
```

```yaml
admins:
  - 123456789        # your Telegram user ID (send /start to @userinfobot to find it)

whisper:
  use_local: true    # true = faster-whisper on CPU (RPi default); false = OpenAI API
  local_model: small
```

### 5. Run migrations

```bash
alembic upgrade head
```

### 6. Start

```bash
python -m bot.main
```

Send `/start` to your bot to confirm it works.

---

## Deployment (systemd, Raspberry Pi 5)

```bash
sudo cp deploy/kb-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable kb-bot
sudo systemctl start kb-bot

# Follow logs
sudo journalctl -u kb-bot -f
```

The bot runs in **polling mode** by default.  
For **webhook mode**, set `WEBHOOK_HOST` in `.env` and expose port 8080 via nginx + Let's Encrypt.

---

## Estimated Costs (personal use, ~200 notes/month)

| Item | Cost |
|---|---|
| Transcription (faster-whisper, local) | $0.00 |
| Embeddings (200 notes + searches) | ~$0.01 |
| Claude — classification + title (200 entries) | ~$0.10 |
| Claude — /ask queries (~50 questions) | ~$0.15 |
| Claude — daily + weekly digests | ~$0.20 |
| **Total** | **~$0.46 / month** |

Prompt caching cuts input-token costs by ~60–70% for `/ask` and `/draft` (warm system-prompt hits).

---

## License

MIT
