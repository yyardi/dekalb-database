import os

# PostgreSQL - equities team's isolated database (trade_tracker)
DB_HOST = os.getenv("DB_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_DB = os.getenv("POSTGRES_DB", "trade_tracker")
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")

# Connection pool sizing
DB_MIN_CONNECTIONS = int(os.getenv("DB_MIN_CONNECTIONS", "2"))
DB_MAX_CONNECTIONS = int(os.getenv("DB_MAX_CONNECTIONS", "10"))

# IBKR Web API (OAuth 2.0) — no local gateway needed
# Setup:
#   1. Register your app at https://interactivebrokers.github.io/cpwebapi/
#   2. Set IBKR_CLIENT_ID, IBKR_CLIENT_SECRET, IBKR_ACCOUNT_ID below
#   3. Set IBKR_REDIRECT_URI to:  https://your-api.railway.app/ibkr/auth/callback
#   4. Set IBKR_ENABLED=true
#   5. Visit /ibkr/auth/login once — team gets IBKR data automatically after that
IBKR_CLIENT_ID = os.getenv("IBKR_CLIENT_ID", "")
IBKR_CLIENT_SECRET = os.getenv("IBKR_CLIENT_SECRET", "")
IBKR_REDIRECT_URI = os.getenv("IBKR_REDIRECT_URI", "http://localhost:8000/ibkr/auth/callback")
IBKR_ACCOUNT_ID = os.getenv("IBKR_ACCOUNT_ID", "")
IBKR_ENABLED = os.getenv("IBKR_ENABLED", "false").lower() == "true"

# IBKR API endpoints — override only if IBKR changes their URLs
IBKR_BASE_URL = os.getenv("IBKR_BASE_URL", "https://api.ibkr.com/v1/api")
IBKR_OAUTH_AUTH_URL = os.getenv("IBKR_OAUTH_AUTH_URL", "https://www.interactivebrokers.com/authorize")
IBKR_OAUTH_TOKEN_URL = os.getenv("IBKR_OAUTH_TOKEN_URL", "https://api.ibkr.com/v1/api/oauth2/token")
IBKR_OAUTH_SCOPE = os.getenv("IBKR_OAUTH_SCOPE", "read:portfolio read:trades read:accounts")

# Frontend URL — used for CORS and post-OAuth redirect
# In production: set to your Vercel app URL, e.g. https://dekalb-tracker.vercel.app
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

# yfinance / market data cache
PRICE_CACHE_TTL_SECONDS = int(os.getenv("PRICE_CACHE_TTL_SECONDS", "60"))

# SPY symbol for benchmark overlay
BENCHMARK_SYMBOL = os.getenv("BENCHMARK_SYMBOL", "SPY")

# FastAPI
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))
DEBUG = os.getenv("DEBUG", "false").lower() == "true"
