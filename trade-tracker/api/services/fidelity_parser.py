"""
Fidelity CSV trade history parser.

Fidelity's exported trade history CSV format (Activity & Orders export):

Row layout:
  "Run Date","Account","Action","Symbol","Security Description",
  "Security Type","Quantity","Price ($)","Commission ($)",
  "Fees ($)","Accrued Interest ($)","Amount ($)","Settlement Date"

Notes:
- The file typically has several header/footer garbage lines before and after
  the actual data rows (Fidelity love doing this).
- We skip rows where Symbol is blank or not a valid equity symbol.
- "Action" maps to BUY/SELL: rows containing "YOU BOUGHT" / "YOU SOLD".
- Amounts in Fidelity CSV use parentheses for negatives: (100.00) = -100.00.

Usage:
    from services.fidelity_parser import parse_fidelity_csv
    trades, errors = parse_fidelity_csv(csv_text, account_id="FIDELITY_001", import_id=1)
"""
from __future__ import annotations

import csv
import io
import logging
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

from models.schemas import TradeCreate

logger = logging.getLogger(__name__)

# Actions that indicate a buy trade
_BUY_KEYWORDS = {"YOU BOUGHT", "BOUGHT", "BUY", "PURCHASE"}
# Actions that indicate a sell trade
_SELL_KEYWORDS = {"YOU SOLD", "SOLD", "SELL"}

# Expected Fidelity column headers (case-insensitive match)
_EXPECTED_COLS = {
    "run date", "account", "action", "symbol",
    "quantity", "price ($)", "commission ($)", "amount ($)",
}


def _parse_fidelity_decimal(raw: str) -> Optional[Decimal]:
    """
    Handle Fidelity's number format:
      - parentheses = negative: (1,234.56) -> -1234.56
      - commas as thousands separator
      - empty / '--' / 'n/a' -> None
    """
    raw = raw.strip().replace(",", "")
    if not raw or raw in ("--", "n/a", "N/A"):
        return None
    negative = False
    if raw.startswith("(") and raw.endswith(")"):
        raw = raw[1:-1]
        negative = True
    elif raw.startswith("-"):
        raw = raw[1:]
        negative = True
    try:
        value = Decimal(raw)
        return -value if negative else value
    except InvalidOperation:
        return None


def _parse_fidelity_date(raw: str) -> Optional[datetime]:
    """Try several date formats Fidelity uses."""
    raw = raw.strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def _detect_side(action: str) -> Optional[str]:
    action_upper = action.upper().strip()
    for kw in _BUY_KEYWORDS:
        if kw in action_upper:
            return "BUY"
    for kw in _SELL_KEYWORDS:
        if kw in action_upper:
            return "SELL"
    return None


def _normalise_header(h: str) -> str:
    return re.sub(r"\s+", " ", h.strip().lower())


def _find_header_row(lines: list[str]) -> Optional[int]:
    """
    Fidelity CSVs have junk at the top. Scan for the line that looks like
    a proper header (contains 'action' and 'symbol').
    """
    for i, line in enumerate(lines):
        lower = line.lower()
        if "action" in lower and "symbol" in lower:
            return i
    return None


def parse_fidelity_csv(
    csv_text: str,
    account_id: str,
    import_id: int,
) -> tuple[list[TradeCreate], list[str]]:
    """
    Parse Fidelity activity CSV text into TradeCreate objects.

    Returns:
        (trades, errors) where errors is a list of human-readable strings
        describing rows that were skipped/failed.
    """
    lines = csv_text.splitlines()
    header_row_idx = _find_header_row(lines)
    if header_row_idx is None:
        return [], ["Could not find header row in CSV. Expected columns: Action, Symbol, Quantity, Price."]

    # Re-parse from header row onward
    data_section = "\n".join(lines[header_row_idx:])
    reader = csv.DictReader(io.StringIO(data_section))

    # Normalise header keys
    if reader.fieldnames is None:
        return [], ["CSV has no columns after header detection."]
    fieldnames_normalised = {_normalise_header(f): f for f in reader.fieldnames if f}

    def col(row: dict, *candidates: str) -> str:
        for candidate in candidates:
            original = fieldnames_normalised.get(candidate)
            if original and original in row:
                return (row[original] or "").strip()
        return ""

    trades: list[TradeCreate] = []
    errors: list[str] = []

    for row_num, row in enumerate(reader, start=header_row_idx + 2):
        # Skip blank / footer rows
        raw_symbol = col(row, "symbol")
        if not raw_symbol or len(raw_symbol) > 10 or not re.match(r"^[A-Z.\-]+$", raw_symbol.upper()):
            continue

        raw_action = col(row, "action")
        side = _detect_side(raw_action)
        if side is None:
            errors.append(f"Row {row_num}: unrecognised action '{raw_action}' for {raw_symbol} - skipped")
            continue

        raw_date = col(row, "run date", "date", "settlement date")
        trade_date = _parse_fidelity_date(raw_date)
        if trade_date is None:
            errors.append(f"Row {row_num}: invalid date '{raw_date}' for {raw_symbol} - skipped")
            continue

        quantity = _parse_fidelity_decimal(col(row, "quantity"))
        if quantity is None or quantity == 0:
            errors.append(f"Row {row_num}: invalid quantity for {raw_symbol} on {raw_date} - skipped")
            continue
        quantity = abs(quantity)

        price = _parse_fidelity_decimal(col(row, "price ($)", "price"))
        if price is None or price <= 0:
            errors.append(f"Row {row_num}: invalid price for {raw_symbol} on {raw_date} - skipped")
            continue

        commission = _parse_fidelity_decimal(col(row, "commission ($)", "commission")) or Decimal("0")
        commission = abs(commission)

        fees = _parse_fidelity_decimal(col(row, "fees ($)", "fees")) or Decimal("0")
        fees = abs(fees)
        total_commission = commission + fees

        gross_amount = (quantity * price).quantize(Decimal("0.01"))
        net_amount_raw = _parse_fidelity_decimal(col(row, "amount ($)", "amount"))
        # Fidelity amount = net already signed; use it if available, else compute
        if net_amount_raw is not None:
            net_amount = net_amount_raw
        else:
            net_amount = (-gross_amount - total_commission) if side == "BUY" else (gross_amount - total_commission)

        raw_data = {k.strip(): v.strip() for k, v in row.items() if k}

        trades.append(
            TradeCreate(
                source="fidelity",
                account_id=account_id,
                trade_date=trade_date,
                symbol=raw_symbol.upper(),
                side=side,
                quantity=quantity,
                price=price,
                commission=total_commission,
                gross_amount=gross_amount,
                net_amount=net_amount,
                label=None,          # user assigns labels manually after import
                is_hedge=False,
                fidelity_import_id=import_id,
                raw_data=raw_data,
            )
        )

    logger.info(
        "Fidelity parse complete: %d trades, %d errors (import_id=%d)",
        len(trades), len(errors), import_id,
    )
    return trades, errors
