"""
IBKR client via Pangolin proxy.

Pangolin is a reverse proxy that handles IBKR OAuth signing.
Your app calls Pangolin with plain HTTPS requests; Pangolin signs them
and forwards to the IBKR Client Portal Web API.

To activate:
  1. Make sure you're connected to the team VPN (Tailscale)
  2. Set IBKR_ENABLED=true in your environment
  3. Set IBKR_ACCOUNT_ID=U1234567 (get from your manager)
  4. Pangolin URL defaults to https://pangolin.dekalb.capital

The API endpoints mirror IBKR's Client Portal Web API v1:
  https://www.interactivebrokers.com/campus/ibkr-api-page/cpapi-v1/
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import requests

import config

logger = logging.getLogger(__name__)

# Shared session — keeps connection alive between calls
_session: Optional[requests.Session] = None


def _get_session() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update({"User-Agent": "dekalb-trade-tracker/1.0"})
    return _session


class IBKRClient:
    """
    Thin wrapper around the IBKR Client Portal Web API, routed through Pangolin.
    All methods return None / [] when IBKR is disabled — callers should handle gracefully.
    """

    def __init__(self) -> None:
        self.base_url = config.IBKR_PANGOLIN_URL.rstrip("/")
        self.enabled = config.IBKR_ENABLED

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get(self, path: str, **kwargs) -> Optional[Any]:
        if not self.enabled:
            return None
        url = f"{self.base_url}{path}"
        try:
            resp = _get_session().get(url, timeout=10, **kwargs)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.ConnectionError:
            logger.error("Cannot reach Pangolin at %s — are you on the VPN?", self.base_url)
            return None
        except requests.exceptions.Timeout:
            logger.error("Pangolin request timed out [%s]", path)
            return None
        except requests.exceptions.HTTPError as exc:
            logger.error("IBKR HTTP error [%s]: %s", path, exc)
            return None
        except Exception as exc:
            logger.error("IBKR request failed [%s]: %s", path, exc)
            return None

    def _post(self, path: str, json: Optional[dict] = None) -> Optional[Any]:
        if not self.enabled:
            return None
        url = f"{self.base_url}{path}"
        try:
            resp = _get_session().post(url, json=json or {}, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.error("IBKR POST failed [%s]: %s", path, exc)
            return None

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def auth_status(self) -> Optional[dict]:
        """
        GET /v1/api/iserver/auth/status
        Returns dict with 'authenticated', 'connected', 'competing' fields.
        """
        return self._get("/v1/api/iserver/auth/status")

    def reauthenticate(self) -> Optional[dict]:
        """POST /v1/api/iserver/reauthenticate — use if session goes stale."""
        return self._post("/v1/api/iserver/reauthenticate")

    # ------------------------------------------------------------------
    # Accounts
    # ------------------------------------------------------------------

    def get_accounts(self) -> list[dict]:
        """
        GET /v1/api/portfolio/accounts
        MUST be called before any per-account portfolio endpoint to warm up the session.
        Returns list of account dicts with 'id', 'accountId', 'type', etc.
        """
        data = self._get("/v1/api/portfolio/accounts")
        if data is None:
            return []
        return data if isinstance(data, list) else [data]

    def get_account_summary(self, account_id: str) -> Optional[dict]:
        """
        GET /v1/api/portfolio/{accountId}/summary
        Returns NAV, cash, equity, margin.

        Key fields (each is a dict with 'amount' and 'currency'):
          netliquidation       -> total NAV
          totalcashvalue       -> cash balance
          equitywithloanvalue  -> equity value
          grosspositionvalue   -> gross market value
        """
        self.get_accounts()  # required warm-up
        return self._get(f"/v1/api/portfolio/{account_id}/summary")

    def get_positions(self, account_id: str) -> list[dict]:
        """
        GET /v1/api/portfolio/{accountId}/positions/0
        Returns list of current open positions.

        Key fields per position:
          ticker / contractDesc  -> symbol
          conid                  -> IBKR contract ID
          position               -> quantity (negative = short)
          mktPrice               -> current market price
          mktValue               -> total market value
          avgCost                -> average cost basis
          unrealizedPnl
          realizedPnl
        """
        self.get_accounts()  # required warm-up
        data = self._get(f"/v1/api/portfolio/{account_id}/positions/0")
        if data is None:
            return []
        return data if isinstance(data, list) else []

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------

    def get_conid(self, symbol: str) -> Optional[int]:
        """
        GET /v1/api/trsrv/stocks?symbols={symbol}
        Look up IBKR contract ID — required before market snapshot calls.
        Response format: {"AAPL": [{"contracts": [{"conid": 265598, ...}]}]}
        """
        data = self._get("/v1/api/trsrv/stocks", params={"symbols": symbol})
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
        """
        GET /v1/api/iserver/marketdata/snapshot?conids={conid}&fields=31,84,86
        Field 31 = last price, 84 = bid, 86 = ask.

        IBKR quirk: first call may return the row with no price yet (subscription
        is being set up). We retry once if that happens.
        """
        params = {"conids": conid, "fields": "31,84,86"}
        data = self._get("/v1/api/iserver/marketdata/snapshot", params=params)
        if not data or not isinstance(data, list):
            return None
        # Retry once if price field is missing (IBKR subscription warm-up)
        if not data[0].get("31"):
            data = self._get("/v1/api/iserver/marketdata/snapshot", params=params)
            if not data or not isinstance(data, list):
                return None
        return data[0]

    # ------------------------------------------------------------------
    # Trade history
    # ------------------------------------------------------------------

    def get_recent_trades(self, account_id: str) -> list[dict]:
        """
        GET /v1/api/iserver/account/trades
        Returns fills from roughly the last 24 hours.

        Key fields per trade:
          execution_id / orderId  -> unique ID (used for dedup)
          symbol / ticker         -> instrument
          side                    -> "BOT" (buy) or "SLD" (sell)
          size                    -> quantity filled
          price                   -> fill price
          commission              -> commissions charged
          trade_time / tradeTime  -> ISO timestamp
        """
        self.get_accounts()  # required warm-up
        data = self._get("/v1/api/iserver/account/trades")
        if data is None:
            return []
        return data if isinstance(data, list) else []


# Singleton — imported by routers and services
ibkr_client = IBKRClient()
