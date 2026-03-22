# DeKalb Database — Monorepo

Backend infrastructure for DeKalb Capital. This repo lives on **Machine 2** (the database server) and handles everything from receiving live trading events to serving the equities team's trade tracker dashboard.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│  MACHINE 1 — Paper Trading Server                       │
│                                                         │
│  Trading Engine                                         │
│    Strategy → Risk Check → IB API                       │
│         │                                               │
│         ▼                                               │
│  Log Aggregator                                         │
│    Orders, Executions, Logs, Signals                    │
│         │                                               │
│         ▼                                               │
│  Bucket (batches events)                                │
│    sends every 1000 events OR 5 seconds                 │
│         │                                               │
│         │  ZMQ PUSH  tcp://machine2:5555               │
└─────────┼───────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────┐
│  MACHINE 2 — Database Server  (this repo)               │
│                                                         │
│  Ingestion Service (ZMQ PULL on port 5555)              │
│         │                                               │
│         ▼                                               │
│       Router                                            │
│      /       \                                          │
│     ▼         ▼                                         │
│  PostgreSQL   QuestDB                                   │
│  (changing)   (time-series)                             │
│                                                         │
│  + Trade Tracker API  →  Equities Team Web App          │
└─────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────┐
│  Equities Team (any browser)                            │
│  https://your-app.vercel.app                            │
│  IBKR data, Fidelity imports, portfolio metrics         │
└─────────────────────────────────────────────────────────┘
```

---

## Repo Structure

```
dekalb-database/
│
├── ingestion-service/              # ZMQ → DB pipeline (quant team)
│   ├── main.py                     # Entry point — ZMQ listener loop
│   ├── router.py                   # Routes events to correct DB writer
│   ├── config.py                   # DB_HOST, ZMQ address, etc.
│   ├── db_writers/
│   │   ├── postgres_writer.py      # Writes to orders + positions tables
│   │   └── questdb_writer.py       # Writes to executions, logs, signals via ILP
│   ├── requirements.txt
│   └── Dockerfile
│
├── trade-tracker/                  # Equities team web app
│   ├── api/                        # FastAPI backend
│   │   ├── main.py
│   │   ├── config.py               # All env var config
│   │   ├── db.py                   # asyncpg connection pool + auto-migrations
│   │   ├── models/schemas.py       # Pydantic request/response models
│   │   ├── routers/
│   │   │   ├── ibkr.py             # /ibkr/* — OAuth connect, account, positions, sync
│   │   │   ├── portfolio.py        # /portfolio/* — summary, positions, metrics
│   │   │   ├── trades.py           # /trades/* — trade log, labels
│   │   │   ├── imports.py          # /import/fidelity — CSV upload
│   │   │   └── market.py           # /market/* — live prices, SPY history
│   │   ├── services/
│   │   │   ├── ibkr_client.py      # IBKR Web API client (OAuth 2.0, no gateway)
│   │   │   ├── market_data.py      # yfinance + IBKR price fetching with cache
│   │   │   ├── portfolio_metrics.py # beta, std dev, sharpe, alpha, drawdown
│   │   │   └── fidelity_parser.py  # Fidelity CSV parser
│   │   ├── requirements.txt
│   │   ├── Dockerfile
│   │   └── railway.toml            # Railway deployment config
│   └── frontend/                   # React + Vite + Tailwind
│       ├── src/
│       │   ├── pages/              # Dashboard, Trades, Import CSV
│       │   └── components/         # Layout, MetricCard, PerformanceChart, etc.
│       ├── vercel.json             # Vercel deployment + API proxy config
│       └── package.json
│
├── schemas/
│   ├── postgresql_schema.sql        # Quant team DB: orders, positions, accounts, strategies
│   ├── questdb_schema.sql           # Quant team time-series: run manually in QuestDB console
│   └── trade_tracker_schema.sql     # Equities team DB: trades, snapshots, imports
│
├── tests/
│   ├── fake_zmq_sender.py           # Send fake events to test ingestion pipeline
│   └── fake_fidelity_export.csv     # Sample Fidelity CSV for testing import
│
├── .env.example                     # Copy to .env and fill in
└── docker-compose.yml               # Runs everything on Machine 2
```

---

## Machine 2 — Quick Start

```bash
# 1. Clone and configure
cp .env.example .env
# Edit .env — at minimum fill in IBKR credentials if you want live data

# 2. Start everything
docker compose up --build

# 3. Verify
curl http://localhost:8000/health

# 4. Open UIs
open http://localhost:3000        # Trade Tracker (equities team)
open http://localhost:8000/docs   # API Swagger docs
open http://localhost:8080        # Adminer DB GUI
open http://localhost:9000        # QuestDB console
```

---

## Services

| Service | Port | What it does |
|---|---|---|
| Trade Tracker Frontend | 3000 | React dashboard — equities team |
| Trade Tracker API | 8000 | FastAPI — Swagger at `/docs` |
| PostgreSQL | 5432 | Relational DB — two isolated databases |
| QuestDB | 9000 | Time-series DB — quant team only |
| QuestDB ILP | 9009 | High-speed ingestion port (write-only) |
| Adminer | 8080 | DB GUI for both databases |
| Ingestion Service | 5555 | ZMQ PULL — receives events from Machine 1 |

---

## Database Design

### Why two databases?

| | PostgreSQL | QuestDB |
|---|---|---|
| **Best for** | State that changes | Append-only time-series |
| **Storage** | Row-based | Columnar |
| **Transactions** | ACID | WAL (write-ahead log) |
| **Indexes** | B-tree | Time-based partitions |
| **Updates** | Yes — UPDATEs are fast | No — append only |
| **Use case** | Orders, positions, accounts | Executions, logs, signals, ticks |

---

### PostgreSQL — `trading` database (quant team)

Connection: `localhost:5432`, database=`trading`, user=`postgres`, password=`postgres`

Schema applied automatically on first boot from `schemas/postgresql_schema.sql`.

#### Tables

**`orders`** — every order from submission to fill

| Column | Type | Description |
|---|---|---|
| order_id | VARCHAR(50) | Unique ID from the trading engine |
| ib_order_id | VARCHAR(50) | IBKR's assigned order ID |
| server_env | VARCHAR(10) | `paper` or `live` |
| symbol | VARCHAR(20) | Ticker (e.g. `AAPL`) |
| side | VARCHAR(4) | `BUY` or `SELL` |
| order_type | VARCHAR(20) | `MKT`, `LMT`, etc. |
| quantity | DECIMAL | Shares ordered |
| limit_price | DECIMAL | Limit price if applicable |
| status | VARCHAR(20) | `SUBMITTED`, `FILLED`, `CANCELLED`, etc. |
| strategy_name | VARCHAR(50) | Which strategy placed this |
| filled_quantity | DECIMAL | How many shares filled so far |
| avg_fill_price | DECIMAL | Average execution price |
| commission | DECIMAL | Commissions charged |

**`positions`** — current holdings (UPSERT on execution)

| Column | Type | Description |
|---|---|---|
| server_env | VARCHAR(10) | `paper` or `live` |
| account_id | VARCHAR(50) | IBKR account |
| symbol | VARCHAR(20) | Ticker |
| quantity | DECIMAL | Net position (negative = short) |
| avg_cost | DECIMAL | Average cost basis |
| unrealized_pnl | DECIMAL | Mark-to-market P&L |

**`accounts`** — account-level balances

**`strategies`** — strategy registry + config (JSONB parameters)

**`ib_api_calls`** — audit log of every IB API call (compliance)

---

### QuestDB — time-series (quant team)

Connection: `localhost:9000` (HTTP console), `localhost:9009` (ILP ingestion)

**Tables must be created manually.** Open `http://localhost:9000`, paste the contents of `schemas/questdb_schema.sql`, and run it. This only needs to happen once.

QuestDB uses its own SQL dialect — do not run this in PostgreSQL.

#### Tables

**`executions`** — every trade fill, append-only

```
timestamp, server_env, order_id, ib_execution_id, symbol, side,
quantity, price, commission, strategy, latency_us
```

**`engine_logs`** — high-volume application logs

```
timestamp, server_env, log_level, component, message, correlation_id, data, latency_us
```

**`strategy_signals`** — when a strategy generates a buy/sell signal

```
timestamp, server_env, strategy, symbol, signal_type, confidence, reason, features
```

**`tick_data`** — market prices (optional, only if storing market data)

```
timestamp, symbol, bid, ask, bid_size, ask_size, last, volume
```

#### QuestDB column types

- `SYMBOL` — low-cardinality strings stored as integers (fast filtering on env, side, strategy, etc.)
- `DOUBLE` — numeric values
- `STRING` — high-cardinality text (messages, reasons)
- `PARTITION BY DAY WAL` — every table partitions data by day and uses write-ahead log for durability

---

### PostgreSQL — `trade_tracker` database (equities team)

Connection: same PostgreSQL instance, database=`trade_tracker`

Schema applied automatically on first boot from `schemas/trade_tracker_schema.sql`. Running tables are auto-migrated on API startup — no manual steps needed.

#### Tables

**`trades`** — unified trade ledger (IBKR + Fidelity)

| Column | Description |
|---|---|
| source | `ibkr` or `fidelity` |
| account_id | Which account |
| symbol | Ticker |
| side | `BUY` or `SELL` |
| quantity / price / commission | Fill details |
| gross_amount | quantity × price |
| net_amount | gross ± commission (signed) |
| label | `event-driven`, `hedge`, `long-term`, `short-term` |
| is_hedge | Boolean flag |
| ibkr_order_id | Links to IBKR for dedup on sync |

**`portfolio_snapshots`** — daily NAV history for charts and metrics

**`fidelity_imports`** — audit log of every CSV upload

**`cash_flows`** — deposits/withdrawals (excluded from performance calc)

**`ibkr_tokens`** — OAuth 2.0 tokens for IBKR Web API (single row, auto-managed)

---

## Ingestion Service (Quant Team)

Receives batched events from Machine 1 over ZMQ and routes them to the right database.

### Event routing

| Event type | PostgreSQL | QuestDB |
|---|---|---|
| `execution` | UPDATE orders + UPSERT positions | INSERT executions |
| `order_update` | UPDATE orders | — |
| `log` | — | INSERT engine_logs |
| `signal` | — | INSERT strategy_signals |

### Testing the pipeline

```bash
# Make sure ingestion-service is running, then:
python tests/fake_zmq_sender.py
# Sends 5 batches of 3 events each (order_update, execution, log)
# Check Adminer at http://localhost:8080 to verify data landed
```

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

---

## Trade Tracker — Equities Team

A Bloomberg-style web dashboard for the equities team. Shows IBKR + Fidelity positions, P&L, portfolio metrics, and performance vs SPY. Team members open a URL — no local setup.

### Running Locally

**Option A — Docker (recommended)**

```bash
docker compose up --build trade-tracker trade-tracker-frontend postgres
```

Frontend at `http://localhost:3000`, API at `http://localhost:8000`.

**Option B — Without Docker**

Terminal 1 — API:
```bash
cd trade-tracker/api
pip install -r requirements.txt
export DB_HOST=localhost
uvicorn main:app --reload --port 8000
```

Terminal 2 — Frontend:
```bash
cd trade-tracker/frontend
npm install && npm run dev
```

> No IBKR credentials needed to run locally. Everything works with yfinance for prices and Fidelity CSV imports. IBKR data is optional on top.

---

### Deploying for the Team (Vercel + Railway)

The full equities team accesses a hosted URL — no one installs anything.

**Step 1 — Deploy API on Railway**

1. Create a project at [railway.app](https://railway.app)
2. Add a PostgreSQL service (Railway generates the connection string)
3. Deploy this repo, set root directory to `trade-tracker/api`
4. Railway picks up `railway.toml` automatically
5. Set environment variables in Railway dashboard:

```
DB_HOST               = (from Railway PostgreSQL service)
POSTGRES_PASSWORD     = (from Railway PostgreSQL service)
POSTGRES_DB           = trade_tracker
IBKR_ENABLED          = true
IBKR_CLIENT_ID        = (from IBKR — see below)
IBKR_CLIENT_SECRET    = (from IBKR — see below)
IBKR_ACCOUNT_ID       = U1234567
IBKR_REDIRECT_URI     = https://YOUR-APP.railway.app/ibkr/auth/callback
FRONTEND_URL          = https://YOUR-APP.vercel.app
```

**Step 2 — Deploy frontend on Vercel**

1. Import repo at [vercel.com](https://vercel.com), root = `trade-tracker/frontend`
2. Edit `trade-tracker/frontend/vercel.json` — replace the placeholder with your Railway URL:

```json
{
  "rewrites": [
    {
      "source": "/api/:path*",
      "destination": "https://YOUR-ACTUAL-RAILWAY-APP.railway.app/:path*"
    },
    {
      "source": "/((?!api/).*)",
      "destination": "/index.html"
    }
  ]
}
```

3. Deploy — team URL is live

**Step 3 — Connect IBKR (one time, ~2 minutes)**

An admin opens the app, clicks **Connect IBKR** in the sidebar, logs in on IBKR's page (normal credentials + 2FA), gets redirected back. Tokens stored in DB — everyone on the team sees live data immediately.

---

### IBKR Web API Setup

The trade tracker uses **IBKR's Web API** — cloud-based OAuth 2.0, no local Java process or gateway required.

**Getting credentials:**

1. Log into [IBKR Client Portal](https://www.interactivebrokers.com/portal/)
2. Go to **Settings → API → Register Application**
   - If you don't see this, contact IBKR support and ask for "Web API / OAuth 2.0 access"
3. Create a new app:
   - Name: anything (e.g. `DeKalb Trade Tracker`)
   - Redirect URI (add both):
     - `http://localhost:8000/ibkr/auth/callback` — for local dev
     - `https://your-api.railway.app/ibkr/auth/callback` — for production
4. IBKR gives you a **Client ID** and **Client Secret** → set as `IBKR_CLIENT_ID` and `IBKR_CLIENT_SECRET`
5. Your **Account ID** is shown top-right in Client Portal (format `U` + digits) → set as `IBKR_ACCOUNT_ID`

---

### Importing Trades

**From Fidelity (CSV)**

1. In Fidelity: Accounts & Trade → Portfolio → select account → Activity & Orders → Download CSV
2. Upload at `POST /import/fidelity` or use the **Import CSV** page in the UI
3. Set an `account_id` label (e.g. `FIDELITY_MAIN`)
4. Trades land unlabeled — use the **Trades** page to categorize them

**From IBKR (live sync)**

Once connected via OAuth, hit `POST /ibkr/sync/trades` — pulls the last ~24h of fills.
For history older than 24h: use IBKR Flex Queries, export as CSV, import the same way as Fidelity.

---

### Trade Tracker API Reference

| Endpoint | What it does |
|---|---|
| `GET /health` | Health check — DB status |
| **IBKR** | |
| `GET /ibkr/status` | Is IBKR connected and authenticated? |
| `GET /ibkr/auth/login` | Returns OAuth URL — redirect user here to connect |
| `GET /ibkr/auth/callback` | IBKR posts here after login — stores tokens |
| `POST /ibkr/auth/disconnect` | Clear IBKR tokens |
| `GET /ibkr/account` | Live NAV, cash, equity from IBKR |
| `GET /ibkr/positions` | Live open positions from IBKR |
| `POST /ibkr/sync/trades` | Pull last ~24h of fills into trades table |
| **Portfolio** | |
| `GET /portfolio/summary` | Combined + per-account P&L snapshot |
| `GET /portfolio/positions` | Open positions with live pricing and P&L |
| `GET /portfolio/performance?period=ytd` | NAV time series + SPY overlay for chart |
| `GET /portfolio/metrics?period=ytd` | Beta, std dev, Sharpe, alpha, drawdown, win rate |
| `POST /portfolio/snapshots/generate` | Compute and store today's NAV snapshot |
| **Trades** | |
| `GET /trades` | Full trade log — filter by symbol, side, label, date |
| `GET /trades/{id}` | Single trade detail |
| `PATCH /trades/{id}/label` | Set label, hedge flag, notes |
| **Imports** | |
| `POST /import/fidelity` | Upload Fidelity CSV |
| `GET /import/fidelity` | List past imports |
| **Market** | |
| `GET /market/quote/{symbol}` | Current price (IBKR or yfinance fallback) |
| `GET /market/quotes?symbols=AAPL,MSFT` | Batch quotes (max 50) |
| `GET /market/history/{symbol}` | Historical OHLCV bars |
| `GET /market/spy` | SPY benchmark data |

Period options for `?period=`: `1m`, `3m`, `6m`, `ytd`, `1y`

Full interactive docs at `/docs` (Swagger UI).

---

### Portfolio Metrics Reference

All metrics are calculated from daily NAV snapshots in `portfolio_snapshots`.
The `snapshot-cron` container generates a snapshot hourly automatically.

NAV excludes deposits and withdrawals — measures pure investment performance only.

| Metric | Formula | Period |
|---|---|---|
| Beta | Cov(portfolio returns, SPY) / Var(SPY) | Rolling 12mo / YTD |
| Std Dev | Daily std dev × √252 | Annualized |
| Sharpe | Annualized return / Annualized std dev | Selected period |
| Alpha | Portfolio return − (Beta × SPY return) | Selected period |
| Max Drawdown | Largest peak-to-trough NAV decline | Selected period |
| Win Rate | % of SELL trades where net proceeds > cost basis | All time |

---

## Adminer — DB GUI

`http://localhost:8080`

| Team | System | Server | Database |
|---|---|---|---|
| Quant | PostgreSQL | postgres | trading |
| Equities | PostgreSQL | postgres | trade_tracker |

User: `postgres` — Password: `postgres`
