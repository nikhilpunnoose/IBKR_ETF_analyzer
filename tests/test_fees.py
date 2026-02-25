from decimal import Decimal

from portfolio_analyzer.analysis.fees import analyze_fees, compute_total_annual_fees


def test_total_annual_fees(sample_portfolio):
    total = compute_total_annual_fees(sample_portfolio)
    # VTI: 28050 * 0.0003 = 8.415, VOO: 25500 * 0.0003 = 7.65, VXUS: 12050 * 0.0005 = 6.025
    expected = (
        Decimal("28050") * Decimal("0.0003")
        + Decimal("25500") * Decimal("0.0003")
        + Decimal("12050") * Decimal("0.0005")
    )
    assert total == expected


def test_cheaper_alternative_found(sample_portfolio):
    fee_alts = {
        "Foreign Large Blend": [
            {"symbol": "IXUS", "expense_ratio": 0.0003},
        ],
    }
    alternatives = analyze_fees(sample_portfolio, fee_alts)
    # VXUS has 0.0005, IXUS has 0.0003 -> savings
    assert len(alternatives) == 1
    alt = alternatives[0]
    assert alt.current_etf == "VXUS"
    assert alt.alternative_etf == "IXUS"
    assert alt.estimated_annual_savings > Decimal(0)


def test_no_alternatives_when_already_cheapest(sample_portfolio):
    fee_alts = {
        "Large Blend": [
            {"symbol": "SCHB", "expense_ratio": 0.0003},
        ],
    }
    alternatives = analyze_fees(sample_portfolio, fee_alts)
    # VTI and VOO are already at 0.0003, same as SCHB
    assert len(alternatives) == 0


def test_no_alternatives_for_stocks(sample_portfolio):
    alternatives = analyze_fees(sample_portfolio, {})
    # AAPL is a stock, not an ETF
    assert not any(a.current_etf == "AAPL" for a in alternatives)
