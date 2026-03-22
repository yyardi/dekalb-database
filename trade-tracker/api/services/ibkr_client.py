"""
IBKR Web API client using OAuth 2.0.

No local gateway needed — authenticates directly with IBKR's cloud API.

Authentication flow (one-time, done by an admin):
  1. Admin visits /ibkr/auth/login in the Trade Tracker
  2. Redirected to IBKR's OAuth login page (standard IBKR login + 2FA)
  3. IBKR redirects back to /ibkr/auth/callback with an auth code
  4. Backend exchanges code for tokens, stores them in DB
  5. Entire team sees live IBKR data — no further action needed

Required environment variables:
  IBKR_CLIENT_ID       - from IBKR developer portal
  IBKR_CLIENT_SECRET   - from IBKR developer portal
  IBKR_REDIRECT_URI    - must match what you registered, e.g.:
                         https://your-api.railway.app/ibkr/auth/callback
  IBKR_ACCOUNT_ID      - your IBKR account ID (U1234567)
  IBKR_ENABLED=true

API reference: https://interactivebrokers.github.io/cpwebapi/
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import urlencode

import requests
import config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory token store
# Loaded from DB at startup, updated after OAuth callback or token refresh.
# ---------------------------------------------------------------------------
_access_token: Optional[str] = None
_refresh_token: Optional[str] = None
_token_expires_at: Optional[datetime] = None
_oauth_state: Optional[str] = None  # CSRF protection for the OAuth flow


def set_token(
    access_token: str,
    refresh_token: Optional[str],
    expires_at: Optional[datetime],
) -> None:
    """Update in-memory token. Called at startup and after OAuth callback."""
    global _access_token, _refresh_token, _token_expires_at
    _access_token = access_token
    _refresh_token = refresh_token
    _token_expires_at = expires_at
    logger.info("IBKR token updated (expires: %s)", expires_at)


def clear_token() -> None:
    global _access_token, _refresh_token, _token_expires_at
    _access_token = None
    _refresh_token = None
    _token_expires_at = None
    logger.warning("IBKR token cleared — re-authentication required")


def is_authenticated() -> bool:
    """True if we have a non-expired access token in memory."""
    if not _access_token:
        return False
    if _token_expires_at and datetime.now(timezone.utc) >= _token_expires_at:
        return False
    return True


# ---------------------------------------------------------------------------
# OAuth helpers (called by the /ibkr/auth/* router endpoints)
# ---------------------------------------------------------------------------

def generate_auth_url() -> str:
    """
    Build the IBKR OAuth authorization URL. Stores a random state value for
    CSRF validation when the callback arrives.
    """
    global _oauth_state
    _oauth_state = secrets.token_urlsafe(32)
    params = {
        "response_type": "code",
        "client_id": config.IBKR_CLIENT_ID,
        "redirect_uri": config.IBKR_REDIRECT_URI,
        "scope": config.IBKR_OAUTH_SCOPE,
        "state": _oauth_state,
    }
    return f"{config.IBKR_OAUTH_AUTH_URL}?{urlencode(params)}"


def validate_state(state: str) -> bool:
    """Return True if the OAuth state matches what we issued (CSRF check)."""
    return bool(_oauth_state) and state == _oauth_state


def exchange_code_for_token(code: str) -> dict:
    """Exchange an authorization code for access + refresh tokens."""
    resp = requests.post(
        config.IBKR_OAUTH_TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": config.IBKR_REDIRECT_URI,
            "client_id": config.IBKR_CLIENT_ID,
            "client_secret": config.IBKR_CLIENT_SECRET,
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def do_token_refresh() -> Optional[dict]:
    """Use the stored refresh token to get a new access token."""
    if not _refresh_token:
        logger.warning("No refresh token — re-authentication required")
        return None
    try:
        resp = requests.post(
            config.IBKR_OAUTH_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": _refresh_token,
                "client_id": config.IBKR_CLIENT_ID,
                "client_secret": config.IBKR_CLIENT_SECRET,
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.error("Token refresh failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# IBKRClient — same interface as before, now pointed at api.ibkr.com
# ---------------------------------------------------------------------------

class IBKRClient:
    """
    Wrapper around the IBKR Web API.
    Identical endpoints to the old Client Portal Gateway — only the base URL
    and auth method changed (Bearer token instead of session cookie).
    """

    def __init__(self) -> None:
        self.base_url = config.IBKR_BASE_URL.rstrip("/")
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": "dekalb-trade-tracker/1.0"})

    def _auth_headers(self) -> dict:
        return {"Authorization": f"Bearer {_access_token}"}

    def _get(self, path: str, **kwargs) -> Optional[Any]:
        if not config.IBKR_ENABLED:
            return None
        if not is_authenticated():
            logger.warning("IBKR not authenticated — visit /ibkr/auth/login")
            return None

        url = f"{self.base_url}{path}"
        try:
            resp = self._session.get(url, headers=self._auth_headers(), timeout=10, **kwargs)

            # On 401, attempt a token refresh and retry once
            if resp.status_code == 401:
                token_data = do_token_refresh()
                if token_data:
                    expires_in = token_data.get("expires_in", 3600)
                    set_token(
                        token_data["access_token"],
                        token_data.get("refresh_token", _refresh_token),
                        datetime.now(timezone.utc) + timedelta(seconds=expires_in),
                    )
                    resp = self._session.get(url, headers=self._auth_headers(), timeout=10, **kwargs)
                else:
                    clear_token()
                    return None

            resp.raise_for_status()
            return resp.json()

        except requests.exceptions.ConnectionError:
            logger.error("Cannot reach IBKR Web API at %s", self.base_url)
            return None
        except requests.exceptions.Timeout:
            logger.error("IBKR Web API request timed out [%s]", path)
            return None
        except requests.exceptions.HTTPError as exc:
            logger.error("IBKR HTTP error [%s]: %s", path, exc)
            return None
        except Exception as exc:
            logger.error("IBKR request failed [%s]: %s", path, exc)
            return None

    def _post(self, path: str, json: Optional[dict] = None) -> Optional[Any]:
        if not config.IBKR_ENABLED or not is_authenticated():
            return None
        url = f"{self.base_url}{path}"
        try:
            resp = self._session.post(url, headers=self._auth_headers(), json=json or {}, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.error("IBKR POST failed [%s]: %s", path, exc)
            return None

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def auth_status(self) -> Optional[dict]:
        return self._get("/iserver/auth/status")

    def reauthenticate(self) -> Optional[dict]:
        return self._post("/iserver/reauthenticate")

    # ------------------------------------------------------------------
    # Accounts
    # ------------------------------------------------------------------

    def get_accounts(self) -> list[dict]:
        data = self._get("/portfolio/accounts")
        if data is None:
            return []
        return data if isinstance(data, list) else [data]

    def get_account_summary(self, account_id: str) -> Optional[dict]:
        self.get_accounts()  # required warm-up per IBKR docs
        return self._get(f"/portfolio/{account_id}/summary")

    def get_positions(self, account_id: str) -> list[dict]:
        self.get_accounts()
        data = self._get(f"/portfolio/{account_id}/positions/0")
        if data is None:
            return []
        return data if isinstance(data, list) else []

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------

    def get_conid(self, symbol: str) -> Optional[int]:
        data = self._get("/trsrv/stocks", params={"symbols": symbol})
        if not data:
            return None
        try:
            contracts = data.get(symbol.upper(), [])
            if contracts:
                return contracts[0]["contracts"][0]["conid"]
        except (KeyError, IndexError, TypeError):
            logger.warning("Unexpected conid response for %s: %s", symbol, data)
        return None

    def get_market_snapshot(self, conid: int) -> Optional[dict]:
        params = {"conids": conid, "fields": "31,84,86"}
        data = self._get("/iserver/marketdata/snapshot", params=params)
        if not data or not isinstance(data, list):
            return None
        if not data[0].get("31"):
            data = self._get("/iserver/marketdata/snapshot", params=params)
            if not data or not isinstance(data, list):
                return None
        return data[0]

    # ------------------------------------------------------------------
    # Trade history
    # ------------------------------------------------------------------

    def get_recent_trades(self, account_id: str) -> list[dict]:
        self.get_accounts()
        data = self._get("/iserver/account/trades")
        if data is None:
            return []
        return data if isinstance(data, list) else []


# Singleton — imported by routers and services
ibkr_client = IBKRClient()
