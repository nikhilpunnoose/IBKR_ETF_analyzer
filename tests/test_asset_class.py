"""Tests for asset class breakdown analysis."""

from datetime import date
from decimal import Decimal

import pytest

from portfolio_analyzer.analysis.asset_class import (
    classify_etf,
    compute_asset_class_breakdown,
)
from portfolio_analyzer.models import (
    AssetClassBucket,
    AssetType,
    ETFHolding,
    ETFInfo,
    Portfolio,
    Position,
)


def _pos(symbol, asset_type, market_value, source="ibkr"):
    return Position(
        symbol=symbol,
        isin=None,
        description=symbol,
        asset_type=asset_type,
        quantity=Decimal(1),
        market_value=Decimal(str(market_value)),
        cost_basis=Decimal(str(market_value)),
        currency="USD",
        mark_price=Decimal(str(market_value)),
        unrealized_pnl=Decimal(0),
        report_date=date(2026, 2, 22),
        source=source,
    )


def _etf_info(symbol, asset_classes, category=None):
    return ETFInfo(
        symbol=symbol,
        name=symbol,
        expense_ratio=0.001,
        category=category,
        family=None,
        top_holdings=[],
        sector_weights={},
        asset_classes=asset_classes,
        total_net_assets=None,
        fetched_at=date(2026, 2, 22),
    )


# --- classify_etf tests ---


def test_classify_stock_etf():
    """An ETF with 99% stocks should classify as 100% equities (cash absorbed)."""
    info = _etf_info("VTI", {"stock": 0.99, "cash": 0.01})
    fracs = classify_etf(info)
    assert fracs[AssetClassBucket.EQUITIES] == pytest.approx(1.0)
    assert fracs[AssetClassBucket.FIXED_INCOME] == pytest.approx(0.0)
    assert fracs[AssetClassBucket.OTHER] == pytest.approx(0.0)


def test_classify_bond_etf():
    """An ETF with 95% bonds should classify as 100% fixed income (cash absorbed)."""
    info = _etf_info("BND", {"bond": 0.95, "cash": 0.05})
    fracs = classify_etf(info)
    assert fracs[AssetClassBucket.EQUITIES] == pytest.approx(0.0)
    assert fracs[AssetClassBucket.FIXED_INCOME] == pytest.approx(1.0)
    assert fracs[AssetClassBucket.OTHER] == pytest.approx(0.0)


def test_classify_mixed_etf():
    """A balanced ETF: cash residual absorbed into the dominant (equity) bucket."""
    info = _etf_info("AOA", {"stock": 0.60, "bond": 0.35, "cash": 0.05})
    fracs = classify_etf(info)
    assert fracs[AssetClassBucket.EQUITIES] == pytest.approx(0.65)  # 0.60 + 0.05 cash
    assert fracs[AssetClassBucket.FIXED_INCOME] == pytest.approx(0.35)
    assert fracs[AssetClassBucket.OTHER] == pytest.approx(0.0)


def test_classify_etf_category_fallback_bond():
    """Empty asset_classes with bond-like category should classify as fixed income."""
    info = _etf_info("AGG", {}, category="Intermediate-Term Bond")
    fracs = classify_etf(info)
    assert fracs[AssetClassBucket.EQUITIES] == pytest.approx(0.0)
    assert fracs[AssetClassBucket.FIXED_INCOME] == pytest.approx(1.0)


def test_classify_etf_category_fallback_equity():
    """Empty asset_classes with equity-like category should classify as equities."""
    info = _etf_info("SPY", {}, category="Large Blend")
    fracs = classify_etf(info)
    assert fracs[AssetClassBucket.EQUITIES] == pytest.approx(1.0)
    assert fracs[AssetClassBucket.FIXED_INCOME] == pytest.approx(0.0)


def test_classify_etf_no_data():
    """No asset_classes and no category should default to equities."""
    info = _etf_info("UNKNOWN", {}, category=None)
    fracs = classify_etf(info)
    assert fracs[AssetClassBucket.EQUITIES] == pytest.approx(1.0)


# --- compute_asset_class_breakdown tests ---


def test_breakdown_stock_position():
    """A direct stock should be 100% equities."""
    portfolio = Portfolio(
        positions=[_pos("AAPL", AssetType.STOCK, 5000)],
        etf_info={},
        total_value=Decimal("5000"),
        report_date=date(2026, 2, 22),
    )
    breakdown = compute_asset_class_breakdown(portfolio)
    assert breakdown.equities_value == Decimal("5000")
    assert breakdown.fixed_income_value == Decimal("0")
    assert breakdown.equities_weight == pytest.approx(1.0)


def test_breakdown_bond_position():
    """A direct bond should be 100% fixed income."""
    portfolio = Portfolio(
        positions=[_pos("BOND-1", AssetType.BOND, 10000)],
        etf_info={},
        total_value=Decimal("10000"),
        report_date=date(2026, 2, 22),
    )
    breakdown = compute_asset_class_breakdown(portfolio)
    assert breakdown.equities_value == Decimal("0")
    assert breakdown.fixed_income_value == Decimal("10000")
    assert breakdown.fixed_income_weight == pytest.approx(1.0)


def test_breakdown_sukuk():
    """Sukuks should classify as fixed income."""
    portfolio = Portfolio(
        positions=[_pos("SUKUK-001", AssetType.SUKUK, 5000, source="enbd")],
        etf_info={},
        total_value=Decimal("5000"),
        report_date=date(2026, 2, 22),
    )
    breakdown = compute_asset_class_breakdown(portfolio)
    assert breakdown.fixed_income_value == Decimal("5000")


def test_breakdown_rsu():
    """RSUs should classify as equities."""
    portfolio = Portfolio(
        positions=[_pos("MSFT", AssetType.RSU, 20000, source="equateplus")],
        etf_info={},
        total_value=Decimal("20000"),
        report_date=date(2026, 2, 22),
    )
    breakdown = compute_asset_class_breakdown(portfolio)
    assert breakdown.equities_value == Decimal("20000")


def test_breakdown_etf_decomposition():
    """A stock ETF should be decomposed into equities based on asset_classes."""
    etf_info = {"VTI": _etf_info("VTI", {"stock": 0.99, "cash": 0.01})}
    portfolio = Portfolio(
        positions=[_pos("VTI", AssetType.ETF, 10000)],
        etf_info=etf_info,
        total_value=Decimal("10000"),
        report_date=date(2026, 2, 22),
    )
    breakdown = compute_asset_class_breakdown(portfolio)
    # Cash residual is absorbed into the dominant (equity) bucket
    assert float(breakdown.equities_value) == pytest.approx(10000, rel=0.01)
    assert float(breakdown.other_value) == pytest.approx(0.0, abs=1)


def test_breakdown_bond_etf_decomposition():
    """A bond ETF should be decomposed into fixed income."""
    etf_info = {"BND": _etf_info("BND", {"bond": 0.95, "cash": 0.05})}
    portfolio = Portfolio(
        positions=[_pos("BND", AssetType.ETF, 10000)],
        etf_info=etf_info,
        total_value=Decimal("10000"),
        report_date=date(2026, 2, 22),
    )
    breakdown = compute_asset_class_breakdown(portfolio)
    # Cash residual is absorbed into the dominant (bond) bucket
    assert float(breakdown.fixed_income_value) == pytest.approx(10000, rel=0.01)
    assert float(breakdown.equities_value) == pytest.approx(0.0)


def test_breakdown_mixed_portfolio():
    """Portfolio with stocks, bonds, and ETFs should sum correctly."""
    etf_info = {
        "VTI": _etf_info("VTI", {"stock": 0.99, "cash": 0.01}),
        "BND": _etf_info("BND", {"bond": 0.95, "cash": 0.05}),
    }
    positions = [
        _pos("AAPL", AssetType.STOCK, 5000),
        _pos("VTI", AssetType.ETF, 10000),
        _pos("BND", AssetType.ETF, 5000),
        _pos("SUKUK-1", AssetType.SUKUK, 2000, source="enbd"),
    ]
    total = sum(p.market_value for p in positions)
    portfolio = Portfolio(
        positions=positions,
        etf_info=etf_info,
        total_value=total,
        report_date=date(2026, 2, 22),
    )
    breakdown = compute_asset_class_breakdown(portfolio)

    # Equities: 5000 (AAPL) + 10000 (VTI, cash residual absorbed) = 15000
    assert float(breakdown.equities_value) == pytest.approx(15000, rel=0.01)
    # Fixed Income: 5000 (BND, cash residual absorbed) + 2000 (SUKUK) = 7000
    assert float(breakdown.fixed_income_value) == pytest.approx(7000, rel=0.01)

    # Weights should sum to ~1.0
    total_weight = breakdown.equities_weight + breakdown.fixed_income_weight + breakdown.other_weight
    assert total_weight == pytest.approx(1.0, abs=0.01)


def test_breakdown_with_override():
    """Manual override should force classification."""
    portfolio = Portfolio(
        positions=[_pos("MYSTERY", AssetType.OTHER, 5000)],
        etf_info={},
        total_value=Decimal("5000"),
        report_date=date(2026, 2, 22),
    )
    # Without override: OTHER -> other bucket
    breakdown = compute_asset_class_breakdown(portfolio)
    assert breakdown.other_value == Decimal("5000")

    # With override: force to equities
    breakdown = compute_asset_class_breakdown(portfolio, overrides={"MYSTERY": "equities"})
    assert breakdown.equities_value == Decimal("5000")
    assert breakdown.other_value == Decimal("0")


def test_breakdown_details_have_source():
    """Detail records should preserve the source field."""
    positions = [
        _pos("AAPL", AssetType.STOCK, 5000, source="ibkr"),
        _pos("MSFT", AssetType.RSU, 20000, source="equateplus"),
    ]
    portfolio = Portfolio(
        positions=positions,
        etf_info={},
        total_value=Decimal("25000"),
        report_date=date(2026, 2, 22),
    )
    breakdown = compute_asset_class_breakdown(portfolio)
    sources = {d.source for d in breakdown.details}
    assert sources == {"ibkr", "equateplus"}


def test_breakdown_crypto_is_other():
    """Crypto should classify as 'other'."""
    portfolio = Portfolio(
        positions=[_pos("BTC", AssetType.CRYPTO, 10000, source="etoro")],
        etf_info={},
        total_value=Decimal("10000"),
        report_date=date(2026, 2, 22),
    )
    breakdown = compute_asset_class_breakdown(portfolio)
    assert breakdown.other_value == Decimal("10000")
    assert breakdown.equities_value == Decimal("0")


def test_breakdown_mixed_currency_converts_to_usd():
    """Non-USD positions must be converted before bucketing so the totals
    match portfolio.total_value (which is already in the base currency)."""
    usd_pos = _pos("AAPL", AssetType.STOCK, 5000)  # USD 5000
    aed_pos = _pos("ENBD_STOCK", AssetType.STOCK, 18380)  # AED 18380 ≈ USD 5002
    # Override currency on the AED position (helper defaults to USD)
    aed_pos = aed_pos.__class__(
        **{**aed_pos.__dict__, "currency": "AED"},
    )
    portfolio = Portfolio(
        positions=[usd_pos, aed_pos],
        etf_info={},
        total_value=Decimal("10002"),
        report_date=date(2026, 2, 22),
    )
    breakdown = compute_asset_class_breakdown(
        portfolio,
        currency_rates={"AED": 0.2723},
        base_currency="USD",
    )
    # Both positions are STOCK → all equities; total ≈ 5000 + 18380*0.2723 ≈ 10003
    assert float(breakdown.equities_value) == pytest.approx(5000 + 18380 * 0.2723, rel=0.01)
    assert breakdown.equities_weight == pytest.approx(1.0)
    assert float(breakdown.fixed_income_value) == pytest.approx(0.0)
