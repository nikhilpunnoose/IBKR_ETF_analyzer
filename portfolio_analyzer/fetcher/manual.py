from __future__ import annotations

import json
import logging
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

from portfolio_analyzer.models import AssetType, ManualPosition, Position

logger = logging.getLogger(__name__)

_LOCAL_DIR = Path("~/.portfolio_analyzer").expanduser()
_LOCAL_FILE = _LOCAL_DIR / "manual_positions.json"


def load_manual_positions(user_id: str | None, source: str) -> list[Position]:
    """Load manual positions and convert to Position objects for analysis.

    Uses Supabase when *user_id* is provided and the client is available,
    otherwise falls back to local JSON storage.
    """
    raw = _load_raw(user_id, source)
    return [manual_to_position(mp) for mp in raw]


def save_manual_positions(
    user_id: str | None, source: str, positions: list[ManualPosition]
) -> None:
    """Persist manual positions (replaces all positions for the given source)."""
    if user_id:
        try:
            _save_supabase(user_id, source, positions)
            return
        except Exception:
            logger.debug("Supabase unavailable, falling back to local storage")

    _save_local(source, positions)


def delete_manual_position(
    user_id: str | None, source: str, position_id: str
) -> None:
    """Remove a single manual position by ID."""
    raw = _load_raw(user_id, source)
    raw = [mp for mp in raw if mp.id != position_id]
    save_manual_positions(user_id, source, raw)


def add_manual_position(
    user_id: str | None, source: str, position: ManualPosition
) -> None:
    """Add a single manual position to the existing list."""
    raw = _load_raw(user_id, source)
    raw.append(position)
    save_manual_positions(user_id, source, raw)


def make_manual_position(
    source: str,
    symbol: str,
    description: str,
    asset_type: str,
    quantity: str,
    market_value: str,
    cost_basis: str,
    currency: str,
    mark_price: str,
    notes: str = "",
    unvested_quantity: str = "0",
    sector: str = "",
) -> ManualPosition:
    """Create a ManualPosition with a generated ID and timestamp."""
    return ManualPosition(
        id=str(uuid.uuid4()),
        source=source,
        symbol=symbol,
        description=description,
        asset_type=asset_type,
        quantity=quantity,
        market_value=market_value,
        cost_basis=cost_basis,
        currency=currency,
        mark_price=mark_price,
        notes=notes,
        unvested_quantity=unvested_quantity,
        updated_at=date.today().isoformat(),
        sector=sector,
    )


def manual_to_position(mp: ManualPosition) -> Position:
    """Convert a ManualPosition to a Position for analysis."""
    try:
        asset_type = AssetType(mp.asset_type)
    except ValueError:
        asset_type = AssetType.OTHER

    market_value = Decimal(mp.market_value)
    cost_basis = Decimal(mp.cost_basis) if mp.cost_basis else market_value
    quantity = Decimal(mp.quantity)
    mark_price = Decimal(mp.mark_price) if mp.mark_price else (
        market_value / quantity if quantity else Decimal(0)
    )

    return Position(
        symbol=mp.symbol,
        isin=None,
        description=mp.description,
        asset_type=asset_type,
        quantity=quantity,
        market_value=market_value,
        cost_basis=cost_basis,
        currency=mp.currency,
        mark_price=mark_price,
        unrealized_pnl=market_value - cost_basis,
        report_date=date.today(),
        source=mp.source,
        sector=mp.sector,
    )


# ---------------------------------------------------------------------------
# Internal: load raw ManualPosition objects
# ---------------------------------------------------------------------------


def _load_raw(user_id: str | None, source: str) -> list[ManualPosition]:
    if user_id:
        try:
            return _load_supabase(user_id, source)
        except Exception:
            logger.debug("Supabase unavailable, falling back to local storage")
    return _load_local(source)


# ---------------------------------------------------------------------------
# Local JSON storage
# ---------------------------------------------------------------------------


def _load_local(source: str) -> list[ManualPosition]:
    if not _LOCAL_FILE.exists():
        return []
    try:
        data = json.loads(_LOCAL_FILE.read_text())
        entries = data.get(source, [])
        return [ManualPosition(**e) for e in entries]
    except Exception:
        logger.warning("Failed to read local manual positions file")
        return []


def _save_local(source: str, positions: list[ManualPosition]) -> None:
    _LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    data: dict = {}
    if _LOCAL_FILE.exists():
        try:
            data = json.loads(_LOCAL_FILE.read_text())
        except Exception:
            data = {}
    data[source] = [_mp_to_dict(mp) for mp in positions]
    _LOCAL_FILE.write_text(json.dumps(data, indent=2))


# ---------------------------------------------------------------------------
# Supabase storage
# ---------------------------------------------------------------------------


def _load_supabase(user_id: str, source: str) -> list[ManualPosition]:
    from supabase import create_client

    import streamlit as st

    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    supabase = create_client(url, key)

    resp = (
        supabase.table("user_manual_positions")
        .select("data_json")
        .eq("user_id", user_id)
        .eq("source", source)
        .execute()
    )
    return [ManualPosition(**row["data_json"]) for row in resp.data]


def _save_supabase(
    user_id: str, source: str, positions: list[ManualPosition]
) -> None:
    from supabase import create_client

    import streamlit as st

    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    supabase = create_client(url, key)

    # Delete existing rows for this user+source
    supabase.table("user_manual_positions").delete().eq(
        "user_id", user_id
    ).eq("source", source).execute()

    # Insert new rows
    for mp in positions:
        supabase.table("user_manual_positions").insert(
            {
                "id": mp.id,
                "user_id": user_id,
                "source": source,
                "data_json": _mp_to_dict(mp),
            }
        ).execute()


def _mp_to_dict(mp: ManualPosition) -> dict:
    return {
        "id": mp.id,
        "source": mp.source,
        "symbol": mp.symbol,
        "description": mp.description,
        "asset_type": mp.asset_type,
        "quantity": mp.quantity,
        "market_value": mp.market_value,
        "cost_basis": mp.cost_basis,
        "currency": mp.currency,
        "mark_price": mp.mark_price,
        "notes": mp.notes,
        "unvested_quantity": mp.unvested_quantity,
        "updated_at": mp.updated_at,
        "sector": mp.sector,
    }
