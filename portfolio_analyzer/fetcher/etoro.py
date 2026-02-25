from __future__ import annotations

import io
import logging
from datetime import date
from decimal import Decimal
from pathlib import Path

import pandas as pd

from portfolio_analyzer.models import AssetType, Position

logger = logging.getLogger(__name__)

_ETORO_TYPE_MAP = {
    "stocks": AssetType.STOCK,
    "etf": AssetType.ETF,
    "crypto": AssetType.CRYPTO,
    "cfd": AssetType.OTHER,
}


def parse_etoro_file(path: str | Path) -> list[Position]:
    """Parse an eToro account statement (XLS/XLSX) into Position objects."""
    return _parse_workbook(pd.ExcelFile(path))


def parse_etoro_bytes(raw: bytes, filename: str) -> list[Position]:
    """Parse uploaded eToro file bytes (for Streamlit)."""
    return _parse_workbook(pd.ExcelFile(io.BytesIO(raw)))


def _parse_workbook(xls: pd.ExcelFile) -> list[Position]:
    """Try sheets in priority order to find current positions."""
    sheets = [s.lower() for s in xls.sheet_names]
    sheet_map = {s.lower(): s for s in xls.sheet_names}

    # Try "Portfolio" sheet first (open positions)
    for candidate in ["portfolio", "open positions"]:
        if candidate in sheets:
            logger.info("Found '%s' sheet in eToro export", sheet_map[candidate])
            return _parse_portfolio_sheet(xls, sheet_map[candidate])

    # Try "Financial Summary" for current holdings snapshot
    if "financial summary" in sheets:
        logger.info("Found 'Financial Summary' sheet in eToro export")
        return _parse_financial_summary(xls, sheet_map["financial summary"])

    # Last resort: closed positions (warn user)
    if "closed positions" in sheets:
        logger.warning(
            "Only 'Closed Positions' found — these are historical trades, "
            "not current holdings. Consider exporting from eToro's Portfolio page."
        )
        return _parse_closed_positions(xls, sheet_map["closed positions"])

    available = ", ".join(xls.sheet_names)
    raise ValueError(
        f"Unrecognized eToro export format. Sheets found: {available}. "
        "Expected a 'Portfolio' or 'Closed Positions' sheet."
    )


def _parse_portfolio_sheet(xls: pd.ExcelFile, sheet_name: str) -> list[Position]:
    """Parse the Portfolio sheet (open/current positions)."""
    df = pd.read_excel(xls, sheet_name=sheet_name)
    df.columns = [c.strip().lower() for c in df.columns]

    positions: list[Position] = []
    for _, row in df.iterrows():
        symbol = _get_col(row, ["instrument name", "instrument", "ticker", "symbol"])
        if not symbol:
            continue

        asset_type_str = str(_get_col(row, ["type", "asset type"]) or "").lower()
        asset_type = _ETORO_TYPE_MAP.get(asset_type_str, AssetType.OTHER)

        units = _to_decimal(_get_col(row, ["units", "units / contracts", "quantity"]))
        invested = _to_decimal(_get_col(row, ["invested", "invested amount", "amount"]))
        value = _to_decimal(_get_col(row, ["value", "equity", "current value"]))
        profit = _to_decimal(_get_col(row, ["profit", "p&l", "profit(usd)", "pnl"]))

        market_value = value if value else invested + profit
        price = market_value / units if units else Decimal(0)

        positions.append(
            Position(
                symbol=str(symbol).strip(),
                isin=str(_get_col(row, ["isin"]) or "").strip() or None,
                description=str(symbol).strip(),
                asset_type=asset_type,
                quantity=units,
                market_value=market_value,
                cost_basis=invested,
                currency="USD",
                mark_price=price,
                unrealized_pnl=profit,
                report_date=date.today(),
                source="etoro",
            )
        )

    logger.info("Parsed %d positions from eToro Portfolio sheet", len(positions))
    return positions


def _parse_financial_summary(xls: pd.ExcelFile, sheet_name: str) -> list[Position]:
    """Parse Financial Summary sheet as a fallback."""
    # Financial Summary is typically aggregated, try to extract what we can
    df = pd.read_excel(xls, sheet_name=sheet_name)
    df.columns = [c.strip().lower() for c in df.columns]

    positions: list[Position] = []
    for _, row in df.iterrows():
        symbol = _get_col(row, ["instrument", "instrument name", "asset", "ticker"])
        if not symbol:
            continue

        value = _to_decimal(_get_col(row, ["value", "amount", "market value"]))
        if not value:
            continue

        positions.append(
            Position(
                symbol=str(symbol).strip(),
                isin=None,
                description=str(symbol).strip(),
                asset_type=AssetType.OTHER,
                quantity=Decimal(1),
                market_value=value,
                cost_basis=value,
                currency="USD",
                mark_price=value,
                unrealized_pnl=Decimal(0),
                report_date=date.today(),
                source="etoro",
            )
        )

    logger.info("Parsed %d positions from eToro Financial Summary", len(positions))
    return positions


def _parse_closed_positions(xls: pd.ExcelFile, sheet_name: str) -> list[Position]:
    """Parse Closed Positions sheet (historical trades, not ideal)."""
    df = pd.read_excel(xls, sheet_name=sheet_name)
    df.columns = [c.strip().lower() for c in df.columns]

    positions: list[Position] = []
    for _, row in df.iterrows():
        action = str(_get_col(row, ["action"]) or "").lower()
        if action not in ("buy", ""):
            continue

        symbol = _get_col(row, ["action", "instrument name", "instrument"])
        # In some formats the instrument name is in a different column
        if not symbol or str(symbol).lower() in ("buy", "sell"):
            symbol = _get_col(row, ["instrument name", "instrument", "ticker"])
        if not symbol:
            continue

        asset_type_str = str(_get_col(row, ["type"]) or "").lower()
        asset_type = _ETORO_TYPE_MAP.get(asset_type_str, AssetType.OTHER)

        units = _to_decimal(_get_col(row, ["units", "units / contracts"]))
        amount = _to_decimal(_get_col(row, ["amount"]))
        close_rate = _to_decimal(_get_col(row, ["close rate"]))
        open_rate = _to_decimal(_get_col(row, ["open rate"]))
        profit = _to_decimal(_get_col(row, ["profit(usd)", "profit"]))

        market_value = units * close_rate if units and close_rate else amount
        cost_basis = units * open_rate if units and open_rate else amount

        positions.append(
            Position(
                symbol=str(symbol).strip(),
                isin=str(_get_col(row, ["isin"]) or "").strip() or None,
                description=str(symbol).strip(),
                asset_type=asset_type,
                quantity=units,
                market_value=market_value,
                cost_basis=cost_basis,
                currency="USD",
                mark_price=close_rate or Decimal(0),
                unrealized_pnl=profit,
                report_date=date.today(),
                source="etoro",
            )
        )

    logger.info("Parsed %d positions from eToro Closed Positions", len(positions))
    return positions


def _get_col(row: pd.Series, candidates: list[str]):
    """Try multiple column name candidates, return first match."""
    for col in candidates:
        if col in row.index:
            val = row[col]
            if pd.notna(val):
                return val
    return None


def _to_decimal(value) -> Decimal:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return Decimal(0)
    try:
        return Decimal(str(value).replace(",", ""))
    except Exception:
        return Decimal(0)
