# DeKalb Database — Monorepo

Backend infrastructure for the DeKalb hedge fund. Houses the database layer, event ingestion pipeline, and trade tracker API.

---

## Repo Structure

```
dekalb-database/
├── ingestion-service/          # ZMQ → PostgreSQL/QuestDB event pipeline
│   ├── main.py                 # Entry point - ZMQ listener
│   ├── router.py               # Event routing logic
│   ├── config.py
│   ├── db_writers/
│   │   ├── postgres_writer.py  # Async asyncpg writer
│   │   └── questdb_writer.py   # ILP writer
│   ├── requirements.txt
│   └── Dockerfile
│
├── trade-tracker/              # Trade tracker REST API (FastAPI)
│   └── api/
│       ├── main.py             # FastAPI app entry point
│       ├── config.py           # Env-var config
│       ├── db.py               # asyncpg connection pool
│       ├── models/
│       │   └── schemas.py      # Pydantic request/response models
│       ├── routers/
│       │   ├── portfolio.py    # /portfolio/* - summary, positions, metrics
│       │   ├── trades.py       # /trades/* - trade log + labeling
│       │   ├── imports.py      # /import/fidelity - CSV upload
│       │   └── market.py       # /market/* - prices + SPY history
│       ├── services/
│       │   ├── market_data.py       # yfinance (+ IBKR gateway stub)
│       │   ├── portfolio_metrics.py # beta, std dev, NAV, sharpe, alpha
│       │   ├── fidelity_parser.py   # Fidelity CSV parser
│       │   └── ibkr_client.py       # IBKR gateway client (stub, enable later)
│       ├── requirements.txt
│       └── Dockerfile
│
├── schemas/
│   ├── postgresql_schema.sql       # Base trading schema (orders, positions, accounts)
│   ├── questdb_schema.sql          # QuestDB time-series schema
│   └── trade_tracker_schema.sql    # Trade tracker tables (trades, snapshots, imports)
│
├── tests/
│   ├── fake_zmq_sender.py          # Send test events to ingestion service
│   └── comprehensive_test.py
│
└── docker-compose.yml              # All services wired together
```

---

## Services

### PostgreSQL (port 5432)
Shared relational database. Stores orders, positions, accounts, and the unified trade ledger.

### QuestDB (port 9000 / 9009)
Time-series database. Stores executions and strategy signals via InfluxDB Line Protocol.

### Ingestion Service (port 5555)
ZMQ PULL socket. Receives trading events from the live IBKR engine and routes them to PostgreSQL + QuestDB.

Event types handled:
- `execution` → PostgreSQL (orders + positions) + QuestDB (executions table)
- `order_update` → PostgreSQL only
- `log` → QuestDB only
- `signal` → QuestDB only

### Trade Tracker API (port 8000)
FastAPI backend for the trade tracker dashboard.

| Endpoint | What it does |
|---|---|
| `GET /portfolio/summary` | Combined + per-account P&L snapshot |
| `GET /portfolio/positions` | Open positions with live P&L |
| `GET /portfolio/performance?period=ytd` | NAV time series + SPY overlay for graph |
| `GET /portfolio/metrics?period=ytd` | Beta, std dev, Sharpe, alpha, max drawdown |
| `GET /trades` | Full trade log with filters |
| `PATCH /trades/{id}/label` | Assign label (event-driven, hedge, long-term, short-term) |
| `POST /import/fidelity` | Upload Fidelity CSV |
| `GET /market/quote/{symbol}` | Current price (yfinance) |
| `GET /market/spy` | SPY historical bars |
| `GET /health` | Service health check |

Swagger UI: `http://localhost:8000/docs`

---

## Quick Start

```bash
# Start all services
docker compose up --build

# In another terminal, send test events to ingestion service
python tests/fake_zmq_sender.py

# API docs
open http://localhost:8000/docs

# Database GUI (adminer)
open http://localhost:8080
# System: PostgreSQL, Server: postgres, User: postgres, Password: postgres, DB: trading
```

---

## Database Schema

The schemas/ directory is auto-loaded by PostgreSQL on first boot (via `/docker-entrypoint-initdb.d`).

```
postgresql_schema.sql       -> orders, positions, accounts, strategies, ib_api_calls
trade_tracker_schema.sql    -> trades, portfolio_snapshots, fidelity_imports, cash_flows
```

Run manually against a live DB:
```bash
psql -h localhost -U postgres -d trading -f schemas/postgresql_schema.sql
psql -h localhost -U postgres -d trading -f schemas/trade_tracker_schema.sql
```

---

## Fidelity CSV Import

1. In Fidelity: Accounts & Trade -> Portfolio -> select account -> Activity & Orders -> Download CSV
2. `POST /import/fidelity` with the file + your `account_id`
3. Trades are loaded unlabeled
4. Label them via `PATCH /trades/{id}/label` with one of: `event-driven`, `hedge`, `long-term`, `short-term`

---

## IBKR Gateway Integration (not yet active)

The IBKR Client Portal Gateway is required for live IBKR data. Currently the service uses yfinance as a fallback.

To enable:
1. Download gateway from https://www.interactivebrokers.com/en/trading/ib-api.php
2. Run it: `./root/run.sh` (Linux/Mac) - authenticates via 2FA, listens on `localhost:5000`
3. Set env vars:
   ```
   IBKR_GATEWAY_ENABLED=true
   IBKR_GATEWAY_URL=https://localhost:5000
   IBKR_ACCOUNT_ID=U1234567
   ```
4. See `trade-tracker/api/services/ibkr_client.py` for all endpoint TODOs

Rate limit: 10 req/sec. Gateway must run on the same machine as the API.

---

## Portfolio Metrics - How They're Calculated

All metrics use daily NAV snapshots stored in `portfolio_snapshots`.

| Metric | Formula |
|---|---|
| **Beta** | Cov(portfolio_returns, SPY_returns) / Var(SPY_returns) |
| **Std Dev** | Daily std dev x sqrt(252) (annualized, 252 trading days) |
| **Sharpe** | Annualized_return / Annualized_std_dev |
| **Alpha** | Portfolio_return - Beta x SPY_return |
| **Max Drawdown** | Max peak-to-trough decline in NAV series |
| **NAV** | Excludes deposits/withdrawals (tracked in cash_flows table) |

SPY data for overlay comes from yfinance and is stored per-snapshot for offline calculations.
