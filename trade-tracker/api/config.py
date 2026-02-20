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

# IBKR Client Portal Gateway
# Run `java -jar ibgateway.jar` locally. 2FA required on startup.
# Set IBKR_GATEWAY_ENABLED=true once the gateway is running.
IBKR_GATEWAY_URL = os.getenv("IBKR_GATEWAY_URL", "https://localhost:5000")
IBKR_GATEWAY_ENABLED = os.getenv("IBKR_GATEWAY_ENABLED", "false").lower() == "true"
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
