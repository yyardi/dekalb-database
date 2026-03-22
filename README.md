# DeKalb Database — Monorepo

Backend infrastructure for DeKalb Capital. Houses the trade tracker (equities team) and the event ingestion pipeline (quant team).

---

## Repo Structure

```
dekalb-database/
├── trade-tracker/              # Trade Tracker — equities team web app
│   ├── api/                    # FastAPI backend
│   │   ├── main.py
│   │   ├── config.py           # All env var config lives here
│   │   ├── db.py               # PostgreSQL connection pool
│   │   ├── models/schemas.py   # Pydantic models
│   │   ├── routers/
│   │   │   ├── portfolio.py    # /portfolio/* — summary, positions, metrics, performance
│   │   │   ├── trades.py       # /trades/* — trade log, labels
│   │   │   ├── imports.py      # /import/fidelity — CSV upload
│   │   │   ├── market.py       # /market/* — live prices, SPY history
│   │   │   └── ibkr.py         # /ibkr/* — OAuth connect, account, positions, sync
│   │   ├── services/
│   │   │   ├── ibkr_client.py       # IBKR Web API client (OAuth 2.0)
│   │   │   ├── market_data.py       # yfinance + IBKR price fetching
│   │   │   ├── portfolio_metrics.py # beta, std dev, sharpe, alpha, drawdown
│   │   │   └── fidelity_parser.py   # Fidelity CSV parser
│   │   ├── requirements.txt
│   │   ├── Dockerfile
│   │   └── railway.toml        # Railway deployment config
│   └── frontend/               # React + Vite + Tailwind dashboard
│       ├── src/
│       │   ├── pages/          # Dashboard, Trades, Import
│       │   └── components/     # Layout, charts, tables, badges
│       ├── vercel.json         # Vercel deployment config
│       └── package.json
│
├── ingestion-service/          # ZMQ → PostgreSQL/QuestDB pipeline (quant team only)
│
├── schemas/
│   ├── trade_tracker_schema.sql    # trades, snapshots, imports, ibkr_tokens
│   ├── postgresql_schema.sql       # quant team DB
│   └── questdb_schema.sql          # quant team time-series
│
└── tests/
    ├── fake_zmq_sender.py      # Test events for ingestion service
    └── fake_fidelity_export.csv
```

---

## Running Locally (Development)

No Railway, no Vercel needed. Two terminals.

### Prerequisites

- Python 3.11+
- Node 18+
- PostgreSQL running locally **or** Docker

### Option A — Docker (easiest)

```bash
docker compose up --build trade-tracker
```

Frontend at `http://localhost:3000` — API at `http://localhost:8000`.

### Option B — Without Docker

**Terminal 1 — API:**

```bash
cd trade-tracker/api
pip install -r requirements.txt

# Set env vars (minimum required for local dev)
export DB_HOST=localhost
export POSTGRES_PASSWORD=postgres

uvicorn main:app --reload --port 8000
```

**Terminal 2 — Frontend:**

```bash
cd trade-tracker/frontend
npm install
npm run dev
```

Frontend at `http://localhost:3000`. The Vite dev server proxies `/api/*` to the API automatically — no CORS config needed locally.

> **No IBKR credentials needed to run locally.** The app falls back to yfinance for all market prices. You can upload Fidelity CSVs and see the full dashboard without touching IBKR at all.

---

## Deploying for the Team (Vercel + Railway)

This is how you get the whole equities team on a hosted URL with no local setup.

### What goes where

| Part | Platform | Cost |
|---|---|---|
| Frontend (React) | Vercel | Free |
| Backend API (FastAPI) | Railway | ~$5-10/mo |
| Database (PostgreSQL) | Railway (add-on) | included |

### Step 1 — Deploy the API on Railway

1. Go to [railway.app](https://railway.app), create a new project
2. Add a **PostgreSQL** service — Railway gives you the connection string
3. Deploy from this repo, set the root directory to `trade-tracker/api`
4. Railway picks up `railway.toml` automatically
5. Set these environment variables in Railway:

```
DB_HOST              = (from Railway Postgres — it shows you this)
POSTGRES_PASSWORD    = (from Railway Postgres)
POSTGRES_DB          = trade_tracker
IBKR_ENABLED         = true
IBKR_CLIENT_ID       = (from IBKR — see section below)
IBKR_CLIENT_SECRET   = (from IBKR — see section below)
IBKR_ACCOUNT_ID      = U1234567
IBKR_REDIRECT_URI    = https://YOUR-APP.railway.app/ibkr/auth/callback
FRONTEND_URL         = https://YOUR-APP.vercel.app
```

### Step 2 — Deploy the frontend on Vercel

1. Go to [vercel.com](https://vercel.com), import this repo
2. Set root directory to `trade-tracker/frontend`
3. Open `trade-tracker/frontend/vercel.json` and replace the placeholder URL with your Railway URL:

```json
{
  "rewrites": [
    {
      "source": "/api/:path*",
      "destination": "https://YOUR-ACTUAL-RAILWAY-URL.railway.app/:path*"
    },
    ...
  ]
}
```

4. Deploy — your team URL is live

### Step 3 — Connect IBKR (one-time, takes 2 minutes)

An admin opens the Trade Tracker, clicks **Connect IBKR** in the sidebar, logs in on IBKR's page (their normal login + 2FA), gets redirected back. Done. Everyone on the team sees IBKR data automatically.

---

## Getting IBKR Web API Credentials

The Trade Tracker uses **IBKR's Web API** — a cloud-based REST API with OAuth 2.0. No local Java process, no gateway, no VPN.

### What you need to get from IBKR

1. Log into [Client Portal](https://www.interactivebrokers.com/portal/)
2. Go to **Settings → API → Register Application** (or search "API" in the settings menu)
3. Create a new OAuth application:
   - Name: `DeKalb Trade Tracker` (or whatever)
   - Redirect URI: `https://YOUR-API.railway.app/ibkr/auth/callback`
   - For local testing, also add: `http://localhost:8000/ibkr/auth/callback`
4. IBKR gives you:
   - **Client ID** → set as `IBKR_CLIENT_ID`
   - **Client Secret** → set as `IBKR_CLIENT_SECRET`
5. Your account ID is on the IBKR portal homepage (top right) — format `U` followed by digits → set as `IBKR_ACCOUNT_ID`

> If you can't find "Register Application" in Client Portal, contact IBKR support and ask for **Web API / OAuth 2.0 access** for your account. Some account types require approval. Individual and institutional accounts both support it.

---

## Trade Tracker API Endpoints

| Endpoint | What it does |
|---|---|
| `GET /health` | Health check |
| `GET /ibkr/status` | Is IBKR connected? |
| `GET /ibkr/auth/login` | Get OAuth URL to connect IBKR |
| `GET /ibkr/auth/callback` | OAuth callback (IBKR posts here after login) |
| `GET /ibkr/account` | Live NAV, cash, equity from IBKR |
| `GET /ibkr/positions` | Live open positions from IBKR |
| `POST /ibkr/sync/trades` | Pull last ~24h of IBKR fills into the trades table |
| `GET /portfolio/summary` | Combined + per-account P&L snapshot |
| `GET /portfolio/positions` | Open positions with live P&L |
| `GET /portfolio/performance?period=ytd` | NAV time series + SPY overlay |
| `GET /portfolio/metrics?period=ytd` | Beta, std dev, Sharpe, alpha, max drawdown |
| `POST /portfolio/snapshots/generate` | Store today's NAV snapshot |
| `GET /trades` | Full trade log with filters |
| `PATCH /trades/{id}/label` | Label a trade (event-driven, hedge, long-term, etc.) |
| `POST /import/fidelity` | Upload Fidelity CSV |
| `GET /market/quote/{symbol}` | Current price |
| `GET /market/spy` | SPY benchmark data |

Swagger UI at `/docs`.

---

## Importing Trades

### Fidelity (CSV upload)

1. In Fidelity: Accounts & Trade → Portfolio → Activity & Orders → Download CSV
2. Upload at `POST /import/fidelity` (or use the Import CSV page in the UI)
3. Set an `account_id` string (e.g. `FIDELITY_MAIN`)
4. Label trades using the Trades page

### IBKR (live sync)

Once connected: hit `POST /ibkr/sync/trades` — pulls last ~24h of fills.
For older history: use IBKR Flex Queries and import the CSV.

---

## Portfolio Metrics

Calculated from daily NAV snapshots (`portfolio_snapshots` table).
The `snapshot-cron` container runs `POST /portfolio/snapshots/generate` hourly.

| Metric | How |
|---|---|
| Beta | Cov(portfolio returns, SPY returns) / Var(SPY returns) |
| Std Dev | Daily std dev × √252 (annualized) |
| Sharpe | Annualized return / Annualized std dev |
| Alpha | Portfolio return − Beta × SPY return |
| Max Drawdown | Largest peak-to-trough NAV decline |

NAV excludes deposits and withdrawals — measures pure investment performance.

---

## Ingestion Service (Quant Team — separate)

ZMQ listener on port 5555. Receives trading events, routes to PostgreSQL and QuestDB.

```bash
python tests/fake_zmq_sender.py  # send test events
```

| Event type | Goes to |
|---|---|
| `execution` | PostgreSQL (orders + positions) + QuestDB |
| `order_update` | PostgreSQL only |
| `log` | QuestDB only |
| `signal` | QuestDB only |

This is completely separate from the Trade Tracker — different database, different service, different team.
