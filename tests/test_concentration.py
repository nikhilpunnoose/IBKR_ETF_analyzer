from portfolio_analyzer.analysis.concentration import analyze_concentration, compute_sector_breakdown
from portfolio_analyzer.analysis.lookthrough import compute_effective_exposures


def test_sector_breakdown_has_technology(sample_portfolio):
    sectors = compute_sector_breakdown(sample_portfolio)
    assert "Technology" in sectors
    assert sectors["Technology"] > 0


def test_single_stock_alert_for_aapl(sample_portfolio):
    exposures = compute_effective_exposures(sample_portfolio)
    # With a low threshold, AAPL should trigger
    alerts = analyze_concentration(
        sample_portfolio, exposures, single_stock_warn=0.01, sector_warn=1.0, top10_warn=1.0
    )
    stock_alerts = [a for a in alerts if a.alert_type == "single_stock"]
    aapl_alerts = [a for a in stock_alerts if "AAPL" in a.entity]
    assert len(aapl_alerts) > 0


def test_no_alerts_with_high_thresholds(sample_portfolio):
    exposures = compute_effective_exposures(sample_portfolio)
    alerts = analyze_concentration(
        sample_portfolio, exposures, single_stock_warn=1.0, sector_warn=1.0, top10_warn=1.0
    )
    assert len(alerts) == 0


def test_sector_alert_with_low_threshold(sample_portfolio):
    exposures = compute_effective_exposures(sample_portfolio)
    alerts = analyze_concentration(
        sample_portfolio, exposures, single_stock_warn=1.0, sector_warn=0.10, top10_warn=1.0
    )
    sector_alerts = [a for a in alerts if a.alert_type == "sector"]
    # Technology is ~30% of VTI/VOO, should trigger at 10% threshold
    assert len(sector_alerts) > 0
    assert any("Technology" in a.entity for a in sector_alerts)
