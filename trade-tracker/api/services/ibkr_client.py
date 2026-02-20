"""
IBKR Client Portal Gateway client.

STATUS: PLACEHOLDER - not yet active.
Set IBKR_GATEWAY_ENABLED=true once the gateway is running.

=============================================================================
HOW TO ENABLE IBKR INTEGRATION
=============================================================================

Step 1: Download & run the Client Portal Gateway
    - Download from: https://www.interactivebrokers.com/en/trading/ib-api.php
      (Client Portal API section, "Download the Gateway")
    - Run: java -jar root/run.sh  (Linux/Mac) or root\\run.bat (Windows)
    - Default URL: https://localhost:5000
    - Gateway requires 2FA login on first start (and after session expires)
    - Keep it running as a systemd service in production

Step 2: Auth flow
    - After starting gateway, navigate to https://localhost:5000 in a browser
    - Log in with your IBKR credentials + 2FA
    - Session lasts ~24 hours; the gateway handles renewal

Step 3: Set environment variables
    - IBKR_GATEWAY_ENABLED=true
    - IBKR_GATEWAY_URL=https://localhost:5000
    - IBKR_ACCOUNT_ID=your_account_id (e.g. U1234567)

Step 4: SSL note
    - Gateway uses a self-signed cert by default
    - You'll need verify=False in requests (or add the cert to trust store)
    - Never expose the gateway externally - it must stay on localhost

=============================================================================
KEY ENDPOINTS (Client Portal Web API v1)
=============================================================================

Auth / session:
  GET  /v1/api/iserver/auth/status          - check if authenticated
  POST /v1/api/iserver/reauthenticate       - re-auth if session stale

Accounts:
  GET  /v1/api/portfolio/accounts           - list accounts (MUST call first)
  GET  /v1/api/portfolio/{acctId}/summary   - NAV, cash, margin
  GET  /v1/api/portfolio/{acctId}/positions/0 - current positions

Market data:
  GET  /v1/api/trsrv/stocks?symbols=AAPL    - lookup contract IDs
  GET  /v1/api/iserver/marketdata/snapshot?conids={conid}&fields=31,84,86
    Field 31 = last price, 84 = bid, 86 = ask

Historical data (for P&L / metrics):
  GET  /v1/api/iserver/marketdata/history?conid={id}&period=1y&bar=1d

Trade history:
  GET  /v1/api/iserver/account/trades       - recent trades (last 24h)
  For longer history: use Flex Queries via Account Management portal

Rate limits: 10 requests/second. Penalty box for 15 min if exceeded.
=============================================================================
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import config

logger = logging.getLogger(__name__)


class IBKRGatewayClient:
    """
    Thin wrapper around the IBKR Client Portal Gateway REST API.
    All methods are no-ops if IBKR_GATEWAY_ENABLED=false.
    """

    def __init__(self) -> None:
        self.base_url = config.IBKR_GATEWAY_URL
        self.enabled = config.IBKR_GATEWAY_ENABLED
        self._session: Any = None  # requests.Session when implemented

    def _not_enabled(self, method: str) -> None:
        logger.warning(
            "IBKR gateway disabled. Set IBKR_GATEWAY_ENABLED=true to use %s.", method
        )

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def auth_status(self) -> Optional[dict]:
        """
        GET /v1/api/iserver/auth/status
        Returns auth status dict or None if gateway disabled.

        TODO: implement with:
            import requests
            resp = self._session.get(f"{self.base_url}/v1/api/iserver/auth/status", verify=False)
            return resp.json()
        """
        if not self.enabled:
            self._not_enabled("auth_status")
            return None
        raise NotImplementedError("IBKR auth_status not yet implemented")

    # ------------------------------------------------------------------
    # Accounts
    # ------------------------------------------------------------------

    def get_accounts(self) -> list[dict]:
        """
        GET /v1/api/portfolio/accounts
        Must be called before any portfolio endpoint to initialize the session.

        TODO: implement and return list of account dicts with 'id', 'accountId', etc.
        """
        if not self.enabled:
            self._not_enabled("get_accounts")
            return []
        raise NotImplementedError("IBKR get_accounts not yet implemented")

    def get_account_summary(self, account_id: str) -> Optional[dict]:
        """
        GET /v1/api/portfolio/{accountId}/summary
        Returns NAV, cash, total equity, margin requirements.

        Key fields to extract:
          totalcashvalue.amount  -> cash_balance
          netliquidation.amount  -> total_nav
          equitywithloanvalue.amount -> equity_value
        """
        if not self.enabled:
            self._not_enabled("get_account_summary")
            return None
        raise NotImplementedError("IBKR get_account_summary not yet implemented")

    def get_positions(self, account_id: str) -> list[dict]:
        """
        GET /v1/api/portfolio/{accountId}/positions/0
        Returns list of current positions.

        Key fields per position:
          conid       -> contract ID
          ticker      -> symbol
          position    -> quantity (negative = short)
          mktPrice    -> current market price
          mktValue    -> market value
          avgCost     -> average cost basis
          unrealizedPnl
          realizedPnl
        """
        if not self.enabled:
            self._not_enabled("get_positions")
            return []
        raise NotImplementedError("IBKR get_positions not yet implemented")

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------

    def get_conid(self, symbol: str) -> Optional[int]:
        """
        GET /v1/api/trsrv/stocks?symbols={symbol}
        Returns the contract ID for a symbol. Required before market data calls.
        """
        if not self.enabled:
            self._not_enabled("get_conid")
            return None
        raise NotImplementedError("IBKR get_conid not yet implemented")

    def get_market_snapshot(self, conid: int) -> Optional[dict]:
        """
        GET /v1/api/iserver/marketdata/snapshot?conids={conid}&fields=31,84,86
        Field 31 = last price, 84 = bid, 86 = ask.
        Note: first call may return empty - call twice (IBKR gateway quirk).
        """
        if not self.enabled:
            self._not_enabled("get_market_snapshot")
            return None
        raise NotImplementedError("IBKR get_market_snapshot not yet implemented")

    # ------------------------------------------------------------------
    # Trade history
    # ------------------------------------------------------------------

    def get_recent_trades(self, account_id: str) -> list[dict]:
        """
        GET /v1/api/iserver/account/trades
        Returns trades from the last ~24 hours.
        For full history, use Flex Queries via the IBKR Account Management portal
        (not available through this API).
        """
        if not self.enabled:
            self._not_enabled("get_recent_trades")
            return []
        raise NotImplementedError("IBKR get_recent_trades not yet implemented")


# Singleton client instance
ibkr_client = IBKRGatewayClient()
