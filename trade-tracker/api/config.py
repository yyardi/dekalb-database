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

# ---------------------------------------------------------------------------
# IBKR Web API — RSA key-based OAuth 2.0 (server-to-server, no browser login)
#
# How it works:
#   Your RSA private key signs a JWT → IBKR returns a bearer token → you
#   create an SSO session with your IBKR username → make API calls.
#   Fully automated. No user action needed. Reconnects on its own.
#
# Paper account:
#   IBKR_CLIENT_ID      = DekalbCapital-Paper
#   IBKR_CLIENT_KEY_ID  = main
#   IBKR_CREDENTIAL     = dekalbcapitalpaper   (the IBKR paper username)
#   IBKR_ACCOUNT_ID     = DFP321877
#
# Live account:
#   IBKR_CLIENT_ID      = (from ticket #619394 — in Ryan's zip)
#   IBKR_CLIENT_KEY_ID  = (from ticket #619394 — in Ryan's zip)
#   IBKR_CREDENTIAL     = (IBKR live username)
#   IBKR_ACCOUNT_ID     = U16303670 or U21601580
#
# IBKR_PRIVATE_KEY: paste the full contents of your privatekey.pem file.
#   In .env, escape newlines as \n  OR  use a literal multiline value.
#   e.g.  IBKR_PRIVATE_KEY="-----BEGIN RSA PRIVATE KEY-----\nMIIE...\n-----END RSA PRIVATE KEY-----"
#
# IBKR_SERVER_IP: the outbound IP of this server as seen by IBKR.
#   Local dev: your public IP (google "what is my ip")
#   Railway:   check Settings → Networking for your static outbound IP
# ---------------------------------------------------------------------------
IBKR_ENABLED = os.getenv("IBKR_ENABLED", "false").lower() == "true"

IBKR_CLIENT_ID     = os.getenv("IBKR_CLIENT_ID", "")       # e.g. DekalbCapital-Paper
IBKR_CLIENT_KEY_ID = os.getenv("IBKR_CLIENT_KEY_ID", "")   # e.g. main
IBKR_CREDENTIAL    = os.getenv("IBKR_CREDENTIAL", "")       # IBKR username
IBKR_ACCOUNT_ID    = os.getenv("IBKR_ACCOUNT_ID", "")       # e.g. DFP321877
IBKR_SERVER_IP     = os.getenv("IBKR_SERVER_IP", "")        # outbound IP of this server

# RSA private key — full PEM content (literal newlines or \n-escaped both work)
_raw_key = os.getenv("IBKR_PRIVATE_KEY", "")
IBKR_PRIVATE_KEY = _raw_key.replace("\\n", "\n")            # normalise escaped newlines

# IBKR API base URLs — don't change these unless IBKR updates them
IBKR_TOKEN_URL       = "https://api.ibkr.com/oauth2/api/v1/token"
IBKR_SSO_URL         = "https://api.ibkr.com/gw/api/v1/sso-sessions"
IBKR_BASE_URL        = "https://api.ibkr.com/v1/api"

# ---------------------------------------------------------------------------
# Frontend URL — used for CORS
# ---------------------------------------------------------------------------
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

# yfinance / market data cache
PRICE_CACHE_TTL_SECONDS = int(os.getenv("PRICE_CACHE_TTL_SECONDS", "60"))

# SPY symbol for benchmark overlay
BENCHMARK_SYMBOL = os.getenv("BENCHMARK_SYMBOL", "SPY")

# FastAPI
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))
DEBUG = os.getenv("DEBUG", "false").lower() == "true"
