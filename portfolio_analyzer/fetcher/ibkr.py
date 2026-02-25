from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from datetime import date
from decimal import Decimal
from pathlib import Path

from ibflex import client

from portfolio_analyzer.models import AssetType, Position

logger = logging.getLogger(__name__)

_ASSET_TYPE_MAP = {
    "STK": AssetType.STOCK,
    "OPT": AssetType.OPTION,
    "BOND": AssetType.BOND,
    "CASH": AssetType.CASH,
}


def fetch_positions(token: str, query_id: str) -> list[Position]:
    """Download and parse an IBKR Flex Query into Position objects."""
    raw_xml = client.download(token, query_id)
    return _parse_xml(raw_xml)


def load_from_file(path: str | Path) -> list[Position]:
    """Parse a previously saved Flex Query XML file."""
    with open(path, "rb") as f:
        raw_xml = f.read()
    return _parse_xml(raw_xml)


def parse_xml_bytes(raw_xml: bytes) -> list[Position]:
    """Parse raw Flex Query XML bytes into Position objects.

    Public wrapper around _parse_xml for use by the web app file uploader.
    """
    return _parse_xml(raw_xml)


def _parse_xml(raw_xml: bytes) -> list[Position]:
    """Parse Flex Query XML, tolerating unknown attributes that ibflex rejects."""
    root = ET.fromstring(raw_xml)
    positions: list[Position] = []

    for stmt in root.iter("FlexStatement"):
        stmt_date_str = stmt.get("toDate", "")
        stmt_date = _parse_date(stmt_date_str) or date.today()

        for op in stmt.iter("OpenPosition"):
            attrs = op.attrib
            positions.append(
                Position(
                    symbol=attrs.get("symbol", ""),
                    isin=attrs.get("isin"),
                    description=attrs.get("description", ""),
                    asset_type=_classify_asset(attrs.get("assetCategory", "")),
                    quantity=_to_decimal(attrs.get("position") or attrs.get("quantity")),
                    market_value=_to_decimal(attrs.get("positionValue")),
                    cost_basis=_to_decimal(attrs.get("costBasisMoney")),
                    currency=attrs.get("currency", "USD"),
                    mark_price=_to_decimal(attrs.get("markPrice")),
                    unrealized_pnl=_to_decimal(
                        attrs.get("fifoPnlUnrealized") or attrs.get("unrealizedPnl")
                    ),
                    report_date=_parse_date(attrs.get("reportDate", "")) or stmt_date,
                    source="ibkr",
                )
            )

    return positions


def _to_decimal(value: str | None) -> Decimal:
    if not value:
        return Decimal(0)
    try:
        return Decimal(value)
    except Exception:
        return Decimal(0)


def _parse_date(value: str) -> date | None:
    if not value:
        return None
    for fmt in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return date.fromisoformat(value) if "-" in value else date(
                int(value[:4]), int(value[4:6]), int(value[6:8])
            )
        except (ValueError, IndexError):
            continue
    return None


def _classify_asset(cat: str) -> AssetType:
    return _ASSET_TYPE_MAP.get(cat, AssetType.OTHER)
