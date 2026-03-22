# DeKalb Database — Monorepo

Backend infrastructure for DeKalb. Houses the database layer, event ingestion pipeline, and trade tracker API.

---

## Repo Structure

```
dekalb-database/
├── ingestion-service/          # ZMQ -> PostgreSQL/QuestDB event pipeline (quant team)
│   ├── main.py                 # ZMQ listener entry point
│   ├── router.py               # Event routing logic
│   ├── config.py
│   ├── db_writers/
│   │   ├── postgres_writer.py
│   │   └── questdb_writer.py
│   ├── requirements.txt
│   └── Dockerfile
│
├── trade-tracker/              # Trade tracker (equities team)
│   ├── api/                    # FastAPI backend
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── db.py               # asyncpg connection pool
│   │   ├── models/schemas.py   # Pydantic models
│   │   ├── routers/
│   │   │   ├── portfolio.py    # /portfolio/*
│   │   │   ├── trades.py       # /trades/*
│   │   │   ├── imports.py      # /import/fidelity
│   │   │   ├── market.py       # /market/*
│   │   │   └── ibkr.py         # /ibkr/*
│   │   ├── services/
│   │   │   ├── ibkr_client.py       # IBKR Client Portal Gateway client
│   │   │   ├── market_data.py       # yfinance (IBKR when gateway is on)
│   │   │   ├── portfolio_metrics.py # beta, std dev, sharpe, alpha
│   │   │   └── fidelity_parser.py   # Fidelity CSV parser
│   │   ├── requirements.txt
│   │   └── Dockerfile
│   └── frontend/               # React + Vite dashboard
│
├── ibkr-gateway/               # IBKR Client Portal Gateway config
│   └── conf.yaml.example       # Copy to conf.yaml
│
├── schemas/
│   ├── postgresql_schema.sql       # orders, positions, accounts (quant team)
│   ├── questdb_schema.sql          # time-series tables (apply via QuestDB console)
│   └── trade_tracker_schema.sql    # trades, snapshots, imports (equities team)
│
├── tests/
│   └── fake_zmq_sender.py      # Send test events to ingestion service
│
├── .env.example                # Copy to .env and fill in your values
└── docker-compose.yml
```

---

## Quick Start

```bash
# 1. Copy env file and fill in your values
cp .env.example .env
# at minimum set IBKR_ACCOUNT_ID if you have it

# 2. Start all services
docker compose up --build

# 3. Check the API
curl http://localhost:8000/health

# 4. Swagger docs
open http://localhost:8000/docs

# 5. Database GUI (Adminer)
open http://localhost:8080
# System: PostgreSQL | Server: postgres | User: postgres | Password: postgres
# Equities DB: trade_tracker  |  Quant DB: trading
```

---

## Services

| Service | Port | What it does |
|---|---|---|
| Trade Tracker API | 8000 | FastAPI backend — Swagger at `/docs` |
| Frontend | 3000 | React dashboard |
| PostgreSQL | 5432 | Main relational DB (two isolated databases) |
| QuestDB | 9000 | Time-series DB (quant team only) |
| Adminer | 8080 | DB GUI |
| Ingestion Service | 5555 | ZMQ listener (quant team) |

---

## Trade Tracker API Endpoints

| Endpoint | What it does |
|---|---|
| `GET /health` | Service health check |
| `GET /portfolio/summary` | Combined + per-account P&L |
| `GET /portfolio/positions` | Open positions with live P&L |
| `GET /portfolio/performance?period=ytd` | NAV time series + SPY overlay |
| `GET /portfolio/metrics?period=ytd` | Beta, std dev, Sharpe, alpha, max drawdown |
| `POST /portfolio/snapshots/generate` | Store today's NAV snapshot |
| `GET /trades` | Full trade log with filters |
| `PATCH /trades/{id}/label` | Label a trade |
| `POST /import/fidelity` | Upload Fidelity CSV |
| `GET /market/quote/{symbol}` | Current price (yfinance or IBKR) |
| `GET /ibkr/status` | Gateway connection status |
| `GET /ibkr/account` | Live NAV + balances from IBKR |
| `GET /ibkr/positions` | Live open positions from IBKR |
| `POST /ibkr/sync/trades` | Pull last 24h of IBKR fills into trades table |

---

## IBKR Gateway Setup

The API works without IBKR — it falls back to **yfinance** for market prices. Enabling IBKR gives you live account data, position sync, and real-time prices.

### How it works

The **IBKR Client Portal Gateway** is a small Java app you run on your machine. You log into it once via browser (username + password + 2FA), and it keeps a session alive. The API talks to it at `https://localhost:5000`.

### Step-by-step

**1. Download the gateway**

Go to: https://www.interactivebrokers.com/en/trading/ib-api.php

Find "Client Portal API" and download the `.zip`. Unzip it into `ibkr-gateway/`:

```
ibkr-gateway/
└── clientportal.gw/
    └── root/
        └── clientportal.gw.jar
```

**2. Copy the config**

```bash
cp ibkr-gateway/conf.yaml.example ibkr-gateway/conf.yaml
```

Default settings work as-is (listens on port 5000).

**3. Start the gateway**

```bash
cd ibkr-gateway
java -jar clientportal.gw/root/clientportal.gw.jar root/conf
```

Leave this terminal open.

**4. Authenticate in your browser**

Open `https://localhost:5000`. Your browser will warn about the self-signed cert — click through it. Log in with your IBKR username/password and complete 2FA.

You'll see a confirmation page when it works. The session lasts ~24 hours. Repeat this step after it expires.

**5. Set env vars in your .env file**

```
IBKR_ENABLED=true
IBKR_ACCOUNT_ID=U1234567
```

Your account ID is on the IBKR homepage after login (top right), format: `U` followed by digits.

**6. Restart the API**

```bash
docker compose up --build trade-tracker
```

**7. Verify**

```bash
curl http://localhost:8000/ibkr/status
# {"enabled": true, "connected": true, "authenticated": true, ...}
```

> **Docker note:** The gateway runs on your host machine. Docker reaches it via `host.docker.internal:5000`, which is already configured in `docker-compose.yml`. No extra steps needed.

---

## Importing Trades

### From Fidelity (CSV)

1. In Fidelity: Accounts & Trade > Portfolio > select account > Activity & Orders > Download CSV
2. `POST /import/fidelity` with the file and an `account_id` string (e.g. `FIDELITY_MAIN`)
3. Trades land unlabeled — use `PATCH /trades/{id}/label` to categorize them
4. Labels: `event-driven`, `hedge`, `long-term`, `short-term`

### From IBKR (live sync)

Once the gateway is running and authenticated: `POST /ibkr/sync/trades`

This pulls the last ~24h of fills. For older history, use IBKR Flex Queries and import the CSV.

---

## Ingestion Service (Quant Team)

Listens on ZMQ port 5555 for trading events from the live engine.

```bash
# Send test events
python tests/fake_zmq_sender.py
```

| Event type | Destination |
|---|---|
| `execution` | PostgreSQL (orders + positions) + QuestDB |
| `order_update` | PostgreSQL only |
| `log` | QuestDB only |
| `signal` | QuestDB only |

---

## Database Schema

PostgreSQL schemas are auto-applied on first boot.

| Database | Schema file | Tables |
|---|---|---|
| `trading` | `postgresql_schema.sql` | orders, positions, accounts, strategies |
| `trade_tracker` | `trade_tracker_schema.sql` | trades, portfolio_snapshots, fidelity_imports, cash_flows |

QuestDB tables are created manually — open `http://localhost:9000` and run `schemas/questdb_schema.sql`.

---

## Portfolio Metrics

Calculated from daily NAV snapshots in `portfolio_snapshots`. The `snapshot-cron` container runs `POST /portfolio/snapshots/generate` every hour automatically.

| Metric | Formula |
|---|---|
| Beta | Cov(portfolio, SPY) / Var(SPY) |
| Std Dev | Daily std dev x sqrt(252) |
| Sharpe | Annualized return / Annualized std dev |
| Alpha | Portfolio return - Beta x SPY return |
| Max Drawdown | Max peak-to-trough NAV decline |
