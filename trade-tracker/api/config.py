import os

# PostgreSQL - equities team's isolated database (trade_tracker)
# The quant team uses the "trading" database; this service connects to "trade_tracker".
DB_HOST = os.getenv("DB_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_DB = os.getenv("POSTGRES_DB", "trade_tracker")
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")

# Connection pool sizing
DB_MIN_CONNECTIONS = int(os.getenv("DB_MIN_CONNECTIONS", "2"))
DB_MAX_CONNECTIONS = int(os.getenv("DB_MAX_CONNECTIONS", "10"))

# IBKR via Pangolin proxy
# Pangolin handles OAuth signing — your app just makes plain HTTP calls to it.
# Set IBKR_ENABLED=true once you have your account ID.
IBKR_PANGOLIN_URL = os.getenv("IBKR_PANGOLIN_URL", "https://pangolin.dekalb.capital")
IBKR_ENABLED = os.getenv("IBKR_ENABLED", "false").lower() == "true"
IBKR_ACCOUNT_ID = os.getenv("IBKR_ACCOUNT_ID", "")

# yfinance / market data cache
# How long to cache price lookups (seconds) before hitting yfinance again
PRICE_CACHE_TTL_SECONDS = int(os.getenv("PRICE_CACHE_TTL_SECONDS", "60"))

# SPY symbol for benchmark overlay
BENCHMARK_SYMBOL = os.getenv("BENCHMARK_SYMBOL", "SPY")

# FastAPI
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))
DEBUG = os.getenv("DEBUG", "false").lower() == "true"
