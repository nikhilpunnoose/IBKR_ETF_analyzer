"""Tests for manual position storage and conversion."""

import json
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from portfolio_analyzer.fetcher.manual import (
    _load_local,
    _save_local,
    make_manual_position,
    manual_to_position,
)
from portfolio_analyzer.models import AssetType, ManualPosition


def test_make_manual_position():
    """make_manual_position should create a ManualPosition with auto-generated ID."""
    mp = make_manual_position(
        source="enbd",
        symbol="2222.SR",
        description="Saudi Aramco",
        asset_type="stock",
        quantity="100",
        market_value="50000",
        cost_basis="45000",
        currency="AED",
        mark_price="500",
    )
    assert mp.source == "enbd"
    assert mp.symbol == "2222.SR"
    assert mp.id  # should have a UUID
    assert mp.updated_at == date.today().isoformat()


def test_manual_to_position_stock():
    """Convert a manual stock position to a Position object."""
    mp = ManualPosition(
        id="test-1",
        source="enbd",
        symbol="AAPL",
        description="Apple Inc",
        asset_type="stock",
        quantity="10",
        market_value="1850",
        cost_basis="1500",
        currency="USD",
        mark_price="185",
    )
    pos = manual_to_position(mp)
    assert pos.symbol == "AAPL"
    assert pos.source == "enbd"
    assert pos.asset_type == AssetType.STOCK
    assert pos.quantity == Decimal("10")
    assert pos.market_value == Decimal("1850")
    assert pos.cost_basis == Decimal("1500")
    assert pos.unrealized_pnl == Decimal("350")
    assert pos.currency == "USD"


def test_manual_to_position_rsu():
    """Convert an RSU position to a Position object."""
    mp = ManualPosition(
        id="test-2",
        source="equateplus",
        symbol="MSFT",
        description="Microsoft Corp",
        asset_type="rsu",
        quantity="500",
        market_value="200000",
        cost_basis="0",
        currency="USD",
        mark_price="400",
        unvested_quantity="200",
    )
    pos = manual_to_position(mp)
    assert pos.asset_type == AssetType.RSU
    assert pos.source == "equateplus"
    assert pos.market_value == Decimal("200000")
    assert pos.cost_basis == Decimal("0")


def test_manual_to_position_sukuk():
    """Convert a sukuk position to a Position object."""
    mp = ManualPosition(
        id="test-3",
        source="enbd",
        symbol="SUKUK-001",
        description="Emirates NBD Sukuk",
        asset_type="sukuk",
        quantity="1",
        market_value="10000",
        cost_basis="10000",
        currency="AED",
        mark_price="10000",
    )
    pos = manual_to_position(mp)
    assert pos.asset_type == AssetType.SUKUK
    assert pos.currency == "AED"


def test_manual_to_position_unknown_type():
    """Unknown asset types should fall back to OTHER."""
    mp = ManualPosition(
        id="test-4",
        source="enbd",
        symbol="MYSTERY",
        description="Unknown Asset",
        asset_type="unicorn",
        quantity="1",
        market_value="100",
        cost_basis="100",
        currency="USD",
        mark_price="100",
    )
    pos = manual_to_position(mp)
    assert pos.asset_type == AssetType.OTHER


def test_local_save_and_load():
    """Test round-trip save/load to local JSON storage."""
    mp = make_manual_position(
        source="enbd",
        symbol="TEST",
        description="Test Position",
        asset_type="stock",
        quantity="10",
        market_value="1000",
        cost_basis="900",
        currency="USD",
        mark_price="100",
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        local_dir = Path(tmpdir)
        local_file = local_dir / "manual_positions.json"

        with patch("portfolio_analyzer.fetcher.manual._LOCAL_DIR", local_dir), \
             patch("portfolio_analyzer.fetcher.manual._LOCAL_FILE", local_file):
            _save_local("enbd", [mp])
            loaded = _load_local("enbd")

            assert len(loaded) == 1
            assert loaded[0].symbol == "TEST"
            assert loaded[0].source == "enbd"
            assert loaded[0].market_value == "1000"

            # Loading a source that doesn't exist should return empty
            empty = _load_local("equateplus")
            assert empty == []


def test_local_load_nonexistent():
    """Loading from a nonexistent file should return empty list."""
    with tempfile.TemporaryDirectory() as tmpdir:
        local_file = Path(tmpdir) / "doesnt_exist.json"
        with patch("portfolio_analyzer.fetcher.manual._LOCAL_FILE", local_file):
            result = _load_local("enbd")
            assert result == []
