from decimal import Decimal

from portfolio_analyzer.analysis.lookthrough import compute_effective_exposures


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
