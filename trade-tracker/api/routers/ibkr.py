"""
IBKR router.

Auth endpoints (OAuth 2.0 — one-time setup by an admin):
  GET  /ibkr/auth/login        - Returns the IBKR OAuth URL; redirect the user there
  GET  /ibkr/auth/callback     - IBKR posts back here after login; stores tokens, redirects to frontend
  POST /ibkr/auth/disconnect   - Clear stored tokens

Data endpoints (available to all team members once connected):
  GET  /ibkr/status            - Connection + auth status
  GET  /ibkr/account           - Live NAV, cash, equity
  GET  /ibkr/positions         - Live open positions
  POST /ibkr/sync/trades       - Pull last ~24h of fills into the trades table
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse

import config
import db
from services.ibkr_client import (
    ibkr_client,
    is_authenticated,
    generate_auth_url,
    validate_state,
    exchange_code_for_token,
    set_token,
    clear_token,
)

router = APIRouter(prefix="/ibkr", tags=["ibkr"])
logger = logging.getLogger(__name__)


def get_pool():
    return db.get_pool()


def _require_ibkr():
    if not config.IBKR_ENABLED:
        raise HTTPException(
            status_code=503,
            detail="IBKR not enabled. Set IBKR_ENABLED=true and configure OAuth credentials.",
        )
    if not is_authenticated():
        raise HTTPException(
            status_code=401,
            detail="IBKR not authenticated. Visit /ibkr/auth/login to connect.",
        )
    if not config.IBKR_ACCOUNT_ID:
        raise HTTPException(
            status_code=503,
            detail="IBKR_ACCOUNT_ID not set in environment.",
        )


# ---------------------------------------------------------------------------
# OAuth — one-time setup flow
# ---------------------------------------------------------------------------

@router.get("/auth/login", summary="Get IBKR OAuth authorization URL")
def auth_login():
    """
    Returns the URL the admin should visit to authenticate with IBKR.
    The frontend should redirect the user to this URL.

    After the user logs in, IBKR will redirect to /ibkr/auth/callback
    and all team members will automatically see IBKR data.
    """
    if not config.IBKR_CLIENT_ID or not config.IBKR_CLIENT_SECRET:
        raise HTTPException(
            status_code=503,
            detail="IBKR_CLIENT_ID and IBKR_CLIENT_SECRET must be set in environment.",
        )
    return {"auth_url": generate_auth_url()}


@router.get("/auth/callback", summary="IBKR OAuth callback — stores tokens and redirects to frontend")
async def auth_callback(code: str, state: str, pool=Depends(get_pool)):
    """
    IBKR redirects here after the user logs in.
    Exchanges the authorization code for tokens, persists them to DB,
    then redirects the user back to the frontend dashboard.
    """
    if not validate_state(state):
        raise HTTPException(status_code=400, detail="Invalid OAuth state — possible CSRF. Try logging in again.")

    try:
        token_data = exchange_code_for_token(code)
    except Exception as exc:
        logger.error("Token exchange failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"IBKR token exchange failed: {exc}")

    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")
    expires_in = token_data.get("expires_in", 3600)
    token_type = token_data.get("token_type", "Bearer")
    scope = token_data.get("scope", "")

    if not access_token:
        raise HTTPException(status_code=502, detail="IBKR did not return an access token.")

    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

    # Persist to DB (single-row upsert on id=1)
    await pool.execute(
        """
        INSERT INTO ibkr_tokens (id, access_token, refresh_token, token_type, expires_at, account_id, scope, updated_at)
        VALUES (1, $1, $2, $3, $4, $5, $6, NOW())
        ON CONFLICT (id) DO UPDATE SET
            access_token  = EXCLUDED.access_token,
            refresh_token = EXCLUDED.refresh_token,
            token_type    = EXCLUDED.token_type,
            expires_at    = EXCLUDED.expires_at,
            account_id    = EXCLUDED.account_id,
            scope         = EXCLUDED.scope,
            updated_at    = NOW()
        """,
        access_token, refresh_token, token_type, expires_at, config.IBKR_ACCOUNT_ID, scope,
    )

    # Update in-memory token so all requests immediately start using it
    set_token(access_token, refresh_token, expires_at)

    logger.info("IBKR OAuth complete — tokens stored. Account: %s", config.IBKR_ACCOUNT_ID)

    # Redirect back to the frontend with a success flag
    return RedirectResponse(url=f"{config.FRONTEND_URL}?ibkr_connected=true")


@router.post("/auth/disconnect", summary="Clear stored IBKR tokens")
async def auth_disconnect(pool=Depends(get_pool)):
    """Remove IBKR tokens from memory and DB."""
    await pool.execute("DELETE FROM ibkr_tokens WHERE id = 1")
    clear_token()
    return {"disconnected": True}


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

@router.get("/status", summary="IBKR connection and auth status")
async def get_status(pool=Depends(get_pool)):
    """
    Returns whether IBKR is connected and authenticated.
    Safe to call at any time — used by the frontend to show the connect button.
    """
    if not config.IBKR_ENABLED:
        return {
            "enabled": False,
            "authenticated": False,
            "message": "Set IBKR_ENABLED=true and configure OAuth credentials to activate.",
        }

    authenticated = is_authenticated()

    # Check if tokens exist in DB even if they haven't been loaded into memory
    if not authenticated:
        row = await pool.fetchrow("SELECT expires_at FROM ibkr_tokens WHERE id = 1")
        if row and row["expires_at"] and row["expires_at"] > datetime.now(timezone.utc):
            # Tokens are in DB but not in memory (e.g. service restarted without startup load)
            authenticated = True

    return {
        "enabled": True,
        "authenticated": authenticated,
        "account_id": config.IBKR_ACCOUNT_ID or "not set",
        "login_url": "/ibkr/auth/login" if not authenticated else None,
        "message": "Connected" if authenticated else "Not connected — visit /ibkr/auth/login",
    }


# ---------------------------------------------------------------------------
# Account summary
# ---------------------------------------------------------------------------

@router.get("/account", summary="Live account NAV and balances from IBKR")
def get_account_summary():
    _require_ibkr()

    summary = ibkr_client.get_account_summary(config.IBKR_ACCOUNT_ID)
    if summary is None:
        raise HTTPException(status_code=502, detail="Could not fetch account summary from IBKR.")

    def extract_amount(field: str) -> Optional[float]:
        entry = summary.get(field, {})
        if isinstance(entry, dict):
            return entry.get("amount")
        return None

    return {
        "account_id": config.IBKR_ACCOUNT_ID,
        "total_nav": extract_amount("netliquidation"),
        "cash_balance": extract_amount("totalcashvalue"),
        "equity_value": extract_amount("equitywithloanvalue"),
        "gross_position_value": extract_amount("grosspositionvalue"),
        "buying_power": extract_amount("buyingpower"),
        "as_of": datetime.utcnow().isoformat() + "Z",
    }


# ---------------------------------------------------------------------------
# Live positions
# ---------------------------------------------------------------------------

@router.get("/positions", summary="Live open positions from IBKR")
def get_live_positions():
    _require_ibkr()

    raw = ibkr_client.get_positions(config.IBKR_ACCOUNT_ID)
    if not raw:
        return []

    positions = []
    for p in raw:
        qty = p.get("position", 0)
        if qty == 0:
            continue
        positions.append({
            "symbol": p.get("ticker") or p.get("contractDesc", "UNKNOWN"),
            "conid": p.get("conid"),
            "quantity": qty,
            "market_price": p.get("mktPrice"),
            "market_value": p.get("mktValue"),
            "avg_cost": p.get("avgCost"),
            "unrealized_pnl": p.get("unrealizedPnl"),
            "realized_pnl": p.get("realizedPnl"),
            "currency": p.get("currency", "USD"),
        })

    return positions


# ---------------------------------------------------------------------------
# Trade sync
# ---------------------------------------------------------------------------

@router.post("/sync/trades", summary="Pull recent IBKR fills into the trades table")
async def sync_recent_trades(pool=Depends(get_pool)):
    """
    Fetches the last ~24 hours of fills from IBKR and inserts any new ones
    into the trades table. Existing trades (matched by ibkr_order_id) are skipped.
    """
    _require_ibkr()

    raw_trades = ibkr_client.get_recent_trades(config.IBKR_ACCOUNT_ID)
    if not raw_trades:
        return {"inserted": 0, "skipped": 0, "total_from_ibkr": 0, "message": "No recent trades returned by IBKR"}

    inserted = 0
    skipped = 0
    errors = []

    for t in raw_trades:
        order_id = str(t.get("execution_id") or t.get("orderId") or "").strip()
        if not order_id:
            skipped += 1
            continue

        existing = await pool.fetchval("SELECT id FROM trades WHERE ibkr_order_id = $1", order_id)
        if existing:
            skipped += 1
            continue

        try:
            raw_side = str(t.get("side", "")).upper()
            side = "BUY" if raw_side in ("BOT", "BUY", "B") else "SELL"

            qty = Decimal(str(t.get("size") or t.get("quantity") or 0))
            price = Decimal(str(t.get("price") or 0))
            commission = Decimal(str(t.get("commission") or 0))

            gross = (qty * price).quantize(Decimal("0.01"))
            net = -(gross + commission) if side == "BUY" else gross - commission

            raw_time = t.get("trade_time") or t.get("tradeTime") or t.get("time")
            if raw_time:
                try:
                    trade_date = datetime.fromisoformat(str(raw_time).replace("Z", "+00:00"))
                except ValueError:
                    trade_date = datetime.utcnow()
            else:
                trade_date = datetime.utcnow()

            symbol = (t.get("symbol") or t.get("ticker") or "").upper().strip()
            if not symbol:
                errors.append(f"Trade {order_id}: missing symbol, skipped")
                skipped += 1
                continue

            await pool.execute(
                """
                INSERT INTO trades
                  (source, account_id, trade_date, symbol, side, quantity, price,
                   commission, gross_amount, net_amount, ibkr_order_id, raw_data)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                """,
                "ibkr", config.IBKR_ACCOUNT_ID, trade_date, symbol, side,
                float(qty), float(price), float(commission),
                float(gross), float(net), order_id, str(t),
            )
            inserted += 1

        except (InvalidOperation, ValueError) as exc:
            msg = f"Trade {order_id}: parse error — {exc}"
            logger.warning(msg)
            errors.append(msg)
            skipped += 1
        except Exception as exc:
            msg = f"Trade {order_id}: DB error — {exc}"
            logger.error(msg)
            errors.append(msg)
            skipped += 1

    logger.info("IBKR sync: inserted=%d skipped=%d errors=%d", inserted, skipped, len(errors))
    return {
        "inserted": inserted,
        "skipped": skipped,
        "total_from_ibkr": len(raw_trades),
        "errors": errors or None,
    }
