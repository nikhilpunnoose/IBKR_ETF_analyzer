from datetime import date
from decimal import Decimal

import pytest

from portfolio_analyzer.analysis.lookthrough import compute_effective_exposures
from portfolio_analyzer.models import AssetType, Portfolio


def test_direct_holding_appears(sample_portfolio):
    exposures = compute_effective_exposures(sample_portfolio)
    aapl = next(e for e in exposures if e.symbol == "AAPL")
    # Direct $5550 + VTI contribution + VOO contribution
    assert aapl.direct_value == Decimal("5550")
    assert aapl.total_value > aapl.direct_value
    assert "VTI" in aapl.etf_contributions
    assert "VOO" in aapl.etf_contributions


def test_etf_lookthrough_values(sample_portfolio):
    exposures = compute_effective_exposures(sample_portfolio)
    aapl = next(e for e in exposures if e.symbol == "AAPL")
    # VTI: 28050 * 0.065 = 1823.25, VOO: 25500 * 0.070 = 1785.00
    expected_vti = Decimal("28050") * Decimal("0.065")
    expected_voo = Decimal("25500") * Decimal("0.070")
    assert aapl.etf_contributions["VTI"] == expected_vti
    assert aapl.etf_contributions["VOO"] == expected_voo
    assert aapl.total_value == Decimal("5550") + expected_vti + expected_voo


def test_sorted_by_total_value(sample_portfolio):
    exposures = compute_effective_exposures(sample_portfolio)
    values = [e.total_value for e in exposures]
    assert values == sorted(values, reverse=True)


def test_portfolio_weights_sum_reasonable(sample_portfolio):
    exposures = compute_effective_exposures(sample_portfolio)
    total_weight = sum(e.weight_of_portfolio for e in exposures)
    # Won't sum to 1.0 because we only have top holdings, but should be < 1.0
    assert 0 < total_weight < 1.0


def test_non_usd_position_weight_uses_converted_value():
    """A non-USD position must have its weight computed in base currency,
    not raw native currency, to avoid weights > 100%."""
    from tests.conftest import _make_position

    # AED position: 18,380 AED * 0.2723 ≈ 5,002 USD
    aed_pos = _make_position("ENR.DE", AssetType.STOCK, market_value=Decimal("18380"))
    # Patch currency to AED (helper defaults to USD)
    aed_pos = aed_pos.__class__(**{**aed_pos.__dict__, "currency": "AED"})
    # Portfolio total_value is already in USD (as produced by consolidate.py)
    portfolio = Portfolio(
        positions=[aed_pos],
        etf_info={},
        total_value=Decimal("5002"),  # ~18380 * 0.2723
        report_date=date(2026, 2, 25),
    )
    exposures = compute_effective_exposures(
        portfolio,
        currency_rates={"AED": 0.2723},
        base_currency="USD",
    )
    assert len(exposures) == 1
    exp = exposures[0]
    # Weight must be ≈1.0, not 18380/5002 ≈ 3.67
    assert exp.weight_of_portfolio == pytest.approx(1.0, rel=0.01)
    # direct_value must be USD-converted, not raw AED
    assert float(exp.direct_value) == pytest.approx(5002, rel=0.01)


def test_rsu_appears_in_exposures():
    """RSU positions must appear in effective exposures just like direct stocks."""
    from tests.conftest import _make_position

    rsu = _make_position("NVDA", AssetType.RSU, market_value=Decimal("20000"))
    portfolio = Portfolio(
        positions=[rsu],
        etf_info={},
        total_value=Decimal("20000"),
        report_date=date(2026, 2, 23),
    )
    exposures = compute_effective_exposures(portfolio)
    assert len(exposures) == 1
    assert exposures[0].symbol == "NVDA"
    assert exposures[0].direct_value == Decimal("20000")
    assert exposures[0].weight_of_portfolio == pytest.approx(1.0)


def test_international_holdings_separate(sample_portfolio):
    exposures = compute_effective_exposures(sample_portfolio)
    symbols = {e.symbol for e in exposures}
    # VXUS holdings should appear
    assert "TSM" in symbols
    assert "ASML" in symbols
    # VXUS holdings should not overlap with VTI/VOO
    tsm = next(e for e in exposures if e.symbol == "TSM")
    assert "VXUS" in tsm.etf_contributions
    assert "VTI" not in tsm.etf_contributions
