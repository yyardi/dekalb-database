# DeKalb Database — Monorepo

Backend infrastructure for DeKalb Capital. Runs on **Machine 2** (database server). Handles live trading event ingestion, portfolio storage, and the equities team's trade tracker dashboard.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  MACHINE 1 — Paper Trading Server                           │
│                                                             │
│  Trading Engine: Strategy → Risk Check → IB API            │
│         │                                                   │
│         ▼                                                   │
│  Log Aggregator  (Orders, Executions, Logs, Signals)        │
│         │                                                   │
│         ▼                                                   │
│  Bucket — batches events, sends every 1000 events or 5s     │
│         │                                                   │
│         │   ZMQ PUSH  →  tcp://machine2:5555               │
└─────────┼───────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────┐
│  MACHINE 2 — Database Server  (this repo)                   │
│                                                             │
│  Ingestion Service (ZMQ PULL port 5555)                     │
│       │                                                     │
│       ▼                                                     │
│     Router                                                  │
│    /       \                                                │
│   ▼         ▼                                               │
│  PostgreSQL   QuestDB                                       │
│  (state)      (time-series)                                 │
│                                                             │
│  Trade Tracker API → Equities team web dashboard            │
└─────────────────────────────────────────────────────────────┘
```

---

## Repo Structure

```
dekalb-database/
│
├── ingestion-service/              # ZMQ → DB pipeline (quant team)
│   ├── main.py                     # Entry point — ZMQ listener loop
│   ├── router.py                   # Routes events to correct DB writer
│   ├── config.py                   # Hosts, ports, ZMQ address
│   ├── db_writers/
│   │   ├── postgres_writer.py      # Writes orders + positions
│   │   └── questdb_writer.py       # Writes executions, logs, signals via ILP
│   ├── requirements.txt
│   └── Dockerfile
│
├── trade-tracker/                  # Equities team web app
│   ├── api/                        # FastAPI backend
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── db.py                   # Connection pool + auto-migrations
│   │   ├── models/schemas.py
│   │   ├── routers/
│   │   │   ├── ibkr.py             # /ibkr/* — OAuth connect, sync trades
│   │   │   ├── portfolio.py        # /portfolio/* — summary, positions, metrics
│   │   │   ├── trades.py           # /trades/* — trade log, labels
│   │   │   ├── imports.py          # /import/fidelity and /import/ibkr
│   │   │   └── market.py           # /market/* — live prices, SPY history
│   │   ├── services/
│   │   │   ├── ibkr_client.py      # IBKR Web API client (OAuth 2.0)
│   │   │   ├── ibkr_parser.py      # IBKR Activity Statement CSV parser
│   │   │   ├── fidelity_parser.py  # Fidelity CSV parser
│   │   │   ├── market_data.py      # yfinance + IBKR price fetching with cache
│   │   │   └── portfolio_metrics.py
│   │   ├── requirements.txt
│   │   ├── Dockerfile
│   │   └── railway.toml
│   └── frontend/                   # React + Vite + Tailwind
│       ├── src/
│       │   ├── pages/              # Dashboard, Trades, Import
│       │   └── components/
│       ├── vercel.json
│       └── package.json
│
├── schemas/
│   ├── postgresql_schema.sql        # Quant team DB (auto-applied on first boot)
│   ├── questdb_schema.sql           # Quant team time-series (run manually in console)
│   └── trade_tracker_schema.sql     # Equities team DB (auto-applied on first boot)
│
├── tests/
│   └── fake_zmq_sender.py           # Sends fake events to test the ingestion pipeline
│
├── .env.example                     # Copy to .env and fill in
└── docker-compose.yml
```

---

## Database Design

### Why two databases on Machine 2?

| | PostgreSQL | QuestDB |
|---|---|---|
| Best for | State that changes | Append-only time-series |
| Storage | Row-based | Columnar |
| Transactions | ACID | WAL |
| Indexes | B-tree | Time-based partitions |
| Updates | Fast UPDATEs | Append only |
| Quant team use | Orders, positions, accounts | Executions, logs, signals, ticks |

---

### PostgreSQL — `trading` database (quant team)

Applied automatically from `schemas/postgresql_schema.sql` on first boot.

| Table | What it holds |
|---|---|
| `orders` | Every order from submission to fill — status, fill price, commission |
| `positions` | Current holdings by account and symbol — UPSERT on each execution |
| `accounts` | Account-level cash, buying power, equity |
| `strategies` | Strategy registry with JSONB parameters |
| `ib_api_calls` | Audit log of every IB API call (compliance) |

---

### QuestDB — time-series (quant team)

Tables must be created manually. Open `http://localhost:9000`, paste `schemas/questdb_schema.sql`, run it. One time only.

| Table | What it holds |
|---|---|
| `executions` | Every trade fill — append-only, partitioned by day |
| `engine_logs` | High-volume application logs |
| `strategy_signals` | Buy/sell signals from strategies |
| `tick_data` | Market prices (optional) |

QuestDB uses `SYMBOL` columns for low-cardinality strings (env, side, strategy) — stored as integers internally for fast filtering. All tables use `PARTITION BY DAY WAL`.

---

### PostgreSQL — `trade_tracker` database (equities team)

Applied automatically from `schemas/trade_tracker_schema.sql` on first boot. Auto-migrated on API startup — no manual steps ever needed.

| Table | What it holds |
|---|---|
| `trades` | Unified trade ledger — IBKR + Fidelity in one table |
| `portfolio_snapshots` | Daily NAV history for performance chart |
| `fidelity_imports` | Audit log of all CSV uploads (Fidelity and IBKR history) |
| `cash_flows` | Deposits/withdrawals (excluded from performance calculations) |
| `ibkr_tokens` | OAuth 2.0 tokens for IBKR Web API — auto-managed |

---

## Ingestion Service (Quant Team)

Receives batched events from Machine 1 over ZMQ PULL and routes them.

### Event routing

| Event type | PostgreSQL | QuestDB |
|---|---|---|
| `execution` | UPDATE orders + UPSERT positions | INSERT executions |
| `order_update` | UPDATE orders | — |
| `log` | — | INSERT engine_logs |
| `signal` | — | INSERT strategy_signals |

### ZMQ message format

```json
{
  "type": "batch",
  "batch_time": "2024-01-15T10:30:00Z",
  "count": 3,
  "events": [
    {
      "type": "execution",
      "timestamp": "2024-01-15T10:30:00Z",
      "server_env": "paper",
      "data": {
        "order_id": "ORD001",
        "symbol": "AAPL",
        "side": "BUY",
        "quantity": 100,
        "price": 185.40,
        "commission": 1.00,
        "strategy": "momentum_v1"
      }
    }
  ]
}
```

### Testing the pipeline

```bash
# With ingestion-service running:
python tests/fake_zmq_sender.py
# Sends 5 batches of 3 events each. Check Adminer at http://localhost:8080.
```

---

## Trade Tracker — Equities Team

A web dashboard for tracking IBKR + Fidelity positions, P&L, and portfolio metrics vs SPY. Team members just open a URL.

### How data gets in

**IBKR (automated after first setup):**
- Connect once via OAuth (button in the sidebar)
- On connect, recent trades sync immediately in the background
- After that, new fills sync automatically every hour — nothing to do

**IBKR full history (one-time):**
- The API only returns recent trades
- For everything before that: export from IBKR → Client Portal → Performance & Reports → Activity Statements → set date range → Format: CSV → Download
- Upload on the **Import** page — duplicates are skipped automatically
- After this upload, the hourly sync handles everything going forward

**Fidelity (manual CSV upload):**
- Export from Fidelity → Accounts & Trade → Portfolio → Activity & Orders → Download
- Upload on the **Import** page
- Upload again whenever you want to pull in new Fidelity trades

---

## Running Locally

### Option A — Docker (recommended, runs everything)

```bash
# 1. Configure
cp .env.example .env
# Edit .env — fill in IBKR credentials if you want live data (optional)

# 2. Start
docker compose up --build

# 3. Check
curl http://localhost:8000/health
```

Services that start:

| Service | URL | What it is |
|---|---|---|
| Trade Tracker | http://localhost:3000 | React dashboard |
| API | http://localhost:8000/docs | Swagger UI |
| Adminer | http://localhost:8080 | DB browser |
| QuestDB | http://localhost:9000 | Time-series console |
| PostgreSQL | localhost:5432 | Direct DB access |
| Ingestion Service | port 5555 | ZMQ PULL for quant events |

IBKR credentials are optional for local dev — everything works with yfinance for prices and Fidelity CSV imports.

### Option B — Without Docker

Terminal 1 — start PostgreSQL locally (or point to any running Postgres), then run the API:
```bash
cd trade-tracker/api
pip install -r requirements.txt
export DB_HOST=localhost POSTGRES_DB=trade_tracker
uvicorn main:app --reload --port 8000
```

Terminal 2 — frontend:
```bash
cd trade-tracker/frontend
npm install
npm run dev
```

Frontend at `http://localhost:5173`, API at `http://localhost:8000`.

---

## Deploying for the Team (Vercel + Railway)

Everyone on the team opens one URL — no one installs anything locally.

### Step 1 — Deploy API on Railway

1. Create a project at [railway.app](https://railway.app)
2. Add a PostgreSQL service (Railway provides the connection string)
3. Connect this GitHub repo, set root directory to `trade-tracker/api`
4. Railway picks up `railway.toml` automatically
5. Set environment variables in the Railway dashboard:

```
DB_HOST               = (from Railway PostgreSQL, e.g. postgres.railway.internal)
POSTGRES_PASSWORD     = (from Railway PostgreSQL)
POSTGRES_DB           = trade_tracker
POSTGRES_USER         = postgres
IBKR_ENABLED          = true
IBKR_CLIENT_ID        = (from IBKR — see setup below)
IBKR_CLIENT_SECRET    = (from IBKR — see setup below)
IBKR_ACCOUNT_ID       = U1234567
IBKR_REDIRECT_URI     = https://YOUR-APP.railway.app/ibkr/auth/callback
FRONTEND_URL          = https://YOUR-APP.vercel.app
```

Note the Railway API URL — you'll need it in the next step.

### Step 2 — Deploy frontend on Vercel

1. Import this repo at [vercel.com](https://vercel.com), root directory = `trade-tracker/frontend`
2. Edit `trade-tracker/frontend/vercel.json` — replace the placeholder with your actual Railway URL:

```json
{
  "rewrites": [
    {
      "source": "/api/:path*",
      "destination": "https://YOUR-ACTUAL-RAILWAY-URL.railway.app/:path*"
    },
    {
      "source": "/((?!api/).*)",
      "destination": "/index.html"
    }
  ]
}
```

3. Deploy — this is the URL you share with the team.

### Step 3 — Connect IBKR (one-time, ~2 min)

An admin opens the deployed URL, clicks **Connect IBKR** in the sidebar, logs in on IBKR's page (normal login + 2FA), gets redirected back. Tokens are stored in the DB. Recent trades sync immediately. Everyone on the team sees live data — no one else needs to do anything.

---

## IBKR Web API Setup

The trade tracker uses IBKR's **Web API** — OAuth 2.0, no local Java process or gateway.

**Getting credentials:**

1. Log into [IBKR Client Portal](https://www.interactivebrokers.com/portal/)
2. Go to **Settings → API → Register Application**
   - If you don't see this: contact IBKR support and ask for "Web API / OAuth 2.0 access"
3. Create an app:
   - Redirect URIs (add both):
     - `http://localhost:8000/ibkr/auth/callback` — for local dev
     - `https://your-api.railway.app/ibkr/auth/callback` — for production
4. You receive a **Client ID** and **Client Secret** → set as `IBKR_CLIENT_ID` and `IBKR_CLIENT_SECRET`
5. Your **Account ID** is shown top-right in Client Portal (format: `U` + digits) → set as `IBKR_ACCOUNT_ID`

---

## Trade Tracker API Reference

Full interactive docs at `/docs` (Swagger UI).

| Endpoint | What it does |
|---|---|
| `GET /health` | Health check |
| **IBKR** | |
| `GET /ibkr/status` | Is IBKR connected? |
| `GET /ibkr/auth/login` | Returns OAuth URL — redirect user here to connect |
| `GET /ibkr/auth/callback` | IBKR posts here after login — stores tokens, triggers initial sync |
| `POST /ibkr/auth/disconnect` | Clear IBKR tokens |
| `GET /ibkr/account` | Live NAV, cash, equity from IBKR |
| `GET /ibkr/positions` | Live open positions from IBKR |
| `POST /ibkr/sync/trades` | Pull recent fills now (also runs automatically every hour) |
| **Portfolio** | |
| `GET /portfolio/summary` | Combined + per-account P&L snapshot |
| `GET /portfolio/positions` | Open positions with live pricing |
| `GET /portfolio/performance?period=ytd` | NAV time series + SPY overlay |
| `GET /portfolio/metrics?period=ytd` | Beta, std dev, Sharpe, alpha, drawdown, win rate |
| `POST /portfolio/snapshots/generate` | Generate today's NAV snapshot (also runs automatically every hour) |
| **Trades** | |
| `GET /trades` | Full trade log — filter by symbol, side, label, date |
| `PATCH /trades/{id}/label` | Set label, hedge flag, notes |
| **Imports** | |
| `POST /import/ibkr` | Upload IBKR Activity Statement CSV (historical data) |
| `POST /import/fidelity` | Upload Fidelity CSV |
| `GET /import/fidelity` | List all past imports |
| **Market** | |
| `GET /market/quote/{symbol}` | Current price (IBKR or yfinance fallback) |
| `GET /market/quotes?symbols=AAPL,MSFT` | Batch quotes |
| `GET /market/spy` | SPY benchmark data |

Period options: `1m`, `3m`, `6m`, `ytd`, `1y`

---

## Adminer — DB Browser

`http://localhost:8080`

| Team | Database |
|---|---|
| Quant | System: PostgreSQL / Server: postgres / DB: **trading** |
| Equities | System: PostgreSQL / Server: postgres / DB: **trade_tracker** |

User: `postgres` — Password: `postgres`
