# KB Bot — Personal Knowledge Base Telegram Bot

A multi-user Telegram bot that transcribes voice messages, stores text notes, and enables semantic search over a personal knowledge base. Designed to run on a **Raspberry Pi 5** (Ubuntu 25.10).

## Features

- 🎙 **Voice → text** — transcribes voice messages via OpenAI Whisper and saves them
- 📝 **Text notes** — saves any text message as a note
- 🔍 **Semantic search** — `/search` finds relevant notes using vector similarity (pgvector)
- 📊 **Weekly digest** — `/summary` generates an AI summary of the past week via Claude
- 📦 **Export** — `/export` downloads all notes as a Markdown file
- 💳 **Subscriptions** — Stripe-based payment with a free trial (10 notes)
- 👥 **Multi-user** — each user has fully isolated data

## Stack

| Layer | Technology |
|---|---|
| Language | Python 3.13 |
| Bot framework | aiogram 3.x (async) |
| Transcription | OpenAI Whisper API (`whisper-1`) |
| Embeddings | OpenAI Embeddings API (`text-embedding-3-small`) |
| Vector search | pgvector (PostgreSQL extension) |
| Relational DB | PostgreSQL 17 |
| AI summaries | Anthropic Claude (`claude-sonnet-4-20250514`) |
| Payments | Stripe (webhook-based) |
| Process manager | systemd |

## Project Structure

```
kb-bot/
├── bot/
│   ├── main.py               # entry point
│   ├── handlers/             # one file per command/message type
│   ├── services/             # Whisper, embeddings, pgvector, Claude, billing
│   ├── db/                   # SQLAlchemy models, session, Alembic migrations
│   └── utils/                # config loader, access middleware, rate limiter
├── config.yaml               # admin IDs, pricing, feature flags
├── .env                      # secrets (never commit)
├── .env.example
├── requirements.txt
├── alembic.ini
└── deploy/
    └── kb-bot.service        # systemd unit
```

## Setup

### 1. System dependencies (Ubuntu 25.10 / PostgreSQL 17)

```bash
sudo apt update
sudo apt install python3-venv ffmpeg postgresql-17-pgvector
```

If `postgresql-17-pgvector` is not available, build from source:

```bash
sudo apt install postgresql-server-dev-17 build-essential git
git clone --branch v0.8.0 https://github.com/pgvector/pgvector.git
cd pgvector && make && sudo make install
```

### 2. Database

```bash
sudo -u postgres createdb kbbot
sudo -u postgres psql -c "CREATE USER myuser WITH PASSWORD 'mypassword';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE kbbot TO myuser;"
```

### 3. Project

```bash
git clone git@github.com:iwozere/e-kb.git
cd e-kb
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 4. Configuration

```bash
cp .env.example .env
nano .env
```

Required values in `.env`:

```
TELEGRAM_BOT_TOKEN=       # from @BotFather
OPENAI_API_KEY=           # for Whisper + embeddings
ANTHROPIC_API_KEY=        # for Claude summaries
DATABASE_URL=postgresql+asyncpg://myuser:mypassword@localhost:5432/kbbot
PAYMENT_HMAC_SECRET=      # random secret: python3 -c "import secrets; print(secrets.token_hex(32))"
```

Stripe keys are only needed if billing is enabled:

```
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=
STRIPE_PRICE_ID=
```

Edit `config.yaml` to add your Telegram user ID to the `admins` list.

### 5. Run migrations

```bash
alembic upgrade head
```

### 6. Start

```bash
python -m bot.main
```

Send `/start` to your bot to confirm it's running.

## Bot Commands

| Command | Access | Description |
|---|---|---|
| `/start` | all | Welcome message |
| `/status` | all | Subscription status and note count |
| `/help` | all | Command list |
| `/search <query>` | paid/admin | Semantic search over your notes |
| `/summary` | paid/admin | AI digest of the past 7 days |
| `/export` | paid/admin | Download all notes as Markdown |
| `/admin_stats` | admin only | Total users, subscriptions, notes |

## Deployment (systemd)

```bash
# Create a dedicated service user
sudo useradd --system --no-create-home --shell /usr/sbin/nologin kbbot
sudo chown -R kbbot:kbbot /opt/e-kb

sudo cp deploy/kb-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable kb-bot
sudo systemctl start kb-bot

# Follow logs
sudo journalctl -u kb-bot -f
```

The bot runs in polling mode by default. For webhook mode, set `WEBHOOK_HOST` in `.env` and expose port 8080 via nginx + Let's Encrypt.

The Stripe webhook endpoint is always available at `http://your-pi:8080/stripe-webhook`.

## Estimated Costs (per paying user/month)

| Item | Cost |
|---|---|
| ~200 voice notes, avg 1 min (Whisper) | ~$1.20 |
| Embeddings (notes + searches) | ~$0.01 |
| 4 weekly summaries (Claude) | ~$0.15 |
| **Total** | **~$1.35** |

At $5/month subscription, margin per user is ~$3.65 before infrastructure.

## License

MIT
