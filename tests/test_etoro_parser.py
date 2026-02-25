"""Tests for the eToro account statement parser."""

from pathlib import Path

from portfolio_analyzer.fetcher.etoro import parse_etoro_file
from portfolio_analyzer.models import AssetType


FIXTURE = Path(__file__).parent / "fixtures" / "sample_etoro_export.xlsx"


def test_parse_portfolio_sheet():
    """Parse the Portfolio sheet from a sample eToro export."""
    positions = parse_etoro_file(FIXTURE)
    assert len(positions) == 4


def test_etoro_source_tag():
    """All eToro positions should have source='etoro'."""
    positions = parse_etoro_file(FIXTURE)
    for p in positions:
        assert p.source == "etoro"


def test_etoro_asset_types():
    """Stocks, ETFs, and crypto should be classified correctly."""
    positions = parse_etoro_file(FIXTURE)
    by_sym = {p.symbol: p for p in positions}

    assert by_sym["AAPL"].asset_type == AssetType.STOCK
    assert by_sym["MSFT"].asset_type == AssetType.STOCK
    assert by_sym["VTI"].asset_type == AssetType.ETF
    assert by_sym["BTC"].asset_type == AssetType.CRYPTO


def test_etoro_values():
    """Market values, cost basis, and P&L should be parsed correctly."""
    positions = parse_etoro_file(FIXTURE)
    by_sym = {p.symbol: p for p in positions}

    aapl = by_sym["AAPL"]
    assert float(aapl.market_value) == 1850.0
    assert float(aapl.cost_basis) == 1500.0
    assert float(aapl.unrealized_pnl) == 350.0
    assert float(aapl.quantity) == 10.0


def test_etoro_isin():
    """ISIN should be parsed when available."""
    positions = parse_etoro_file(FIXTURE)
    by_sym = {p.symbol: p for p in positions}

    assert by_sym["AAPL"].isin == "US0378331005"
    # BTC has empty ISIN in fixture
    assert by_sym["BTC"].isin is None or by_sym["BTC"].isin == ""


def test_etoro_currency_default_usd():
    """eToro positions should default to USD."""
    positions = parse_etoro_file(FIXTURE)
    for p in positions:
        assert p.currency == "USD"
