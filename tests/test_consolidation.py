"""Tests for multi-source portfolio consolidation."""

from datetime import date
from decimal import Decimal

from portfolio_analyzer.fetcher.consolidate import (
    build_consolidated_portfolio,
    to_base_currency,
)
from portfolio_analyzer.models import AssetType, Position

import pytest


def _pos(symbol, market_value, source="ibkr", currency="USD"):
    return Position(
        symbol=symbol,
        isin=None,
        description=symbol,
        asset_type=AssetType.STOCK,
        quantity=Decimal(1),
        market_value=Decimal(str(market_value)),
        cost_basis=Decimal(str(market_value)),
        currency=currency,
        mark_price=Decimal(str(market_value)),
        unrealized_pnl=Decimal(0),
        report_date=date(2026, 2, 22),
        source=source,
    )


def test_consolidate_single_source():
    """A single source should produce a portfolio with those positions."""
    positions = [_pos("AAPL", 5000), _pos("MSFT", 3000)]
    portfolio = build_consolidated_portfolio(
        sources={"ibkr": positions},
        etf_info={},
    )
    assert len(portfolio.positions) == 2
    assert portfolio.total_value == Decimal("8000")


def test_consolidate_multiple_sources():
    """Multiple sources should all be merged into one portfolio."""
    ibkr = [_pos("AAPL", 5000, source="ibkr")]
    etoro = [_pos("MSFT", 3000, source="etoro")]
    enbd = [_pos("2222.SR", 10000, source="enbd")]

    portfolio = build_consolidated_portfolio(
        sources={"ibkr": ibkr, "etoro": etoro, "enbd": enbd},
        etf_info={},
    )
    assert len(portfolio.positions) == 3
    assert portfolio.total_value == Decimal("18000")


def test_consolidate_no_deduplication():
    """Same stock from two brokers should NOT be deduplicated."""
    ibkr = [_pos("AAPL", 5000, source="ibkr")]
    etoro = [_pos("AAPL", 3000, source="etoro")]

    portfolio = build_consolidated_portfolio(
        sources={"ibkr": ibkr, "etoro": etoro},
        etf_info={},
    )
    assert len(portfolio.positions) == 2
    assert portfolio.total_value == Decimal("8000")

    # Both positions should retain their source tags
    sources = {p.source for p in portfolio.positions}
    assert sources == {"ibkr", "etoro"}


def test_currency_conversion_aed_to_usd():
    """AED positions should be converted to USD for total_value."""
    rates = {"AED": 0.2723}
    enbd = [_pos("2222.SR", 10000, source="enbd", currency="AED")]

    portfolio = build_consolidated_portfolio(
        sources={"enbd": enbd},
        etf_info={},
        currency_rates=rates,
    )
    # 10000 AED * 0.2723 = 2723 USD
    assert float(portfolio.total_value) == pytest.approx(2723.0, rel=0.01)


def test_mixed_currency_total():
    """Mixed USD and AED positions should sum correctly in base currency."""
    rates = {"AED": 0.2723}
    ibkr = [_pos("AAPL", 5000, source="ibkr", currency="USD")]
    enbd = [_pos("2222.SR", 10000, source="enbd", currency="AED")]

    portfolio = build_consolidated_portfolio(
        sources={"ibkr": ibkr, "enbd": enbd},
        etf_info={},
        currency_rates=rates,
    )
    # 5000 + (10000 * 0.2723) = 5000 + 2723 = 7723
    assert float(portfolio.total_value) == pytest.approx(7723.0, rel=0.01)


def test_to_base_currency_usd_passthrough():
    """USD should pass through unchanged."""
    result = to_base_currency(Decimal("1000"), "USD", {})
    assert result == Decimal("1000")


def test_to_base_currency_missing_rate():
    """Missing currency rate should raise ValueError."""
    with pytest.raises(ValueError, match="No exchange rate"):
        to_base_currency(Decimal("1000"), "GBP", {})


def test_consolidate_empty_sources():
    """Empty sources dict should produce an empty portfolio."""
    portfolio = build_consolidated_portfolio(
        sources={},
        etf_info={},
    )
    assert len(portfolio.positions) == 0
    assert portfolio.total_value == Decimal("0")
