from __future__ import annotations

from portfolio_analyzer.models import ConcentrationAlert, EffectiveExposure, Portfolio


def analyze_concentration(
    portfolio: Portfolio,
    effective_exposures: list[EffectiveExposure],
    single_stock_warn: float = 0.05,
    sector_warn: float = 0.30,
    top10_warn: float = 0.40,
) -> list[ConcentrationAlert]:
    """Check for single-stock, sector, and top-10 concentration risks."""
    alerts: list[ConcentrationAlert] = []
    total = float(portfolio.total_value) if portfolio.total_value else 1.0

    # Single-stock concentration
    for exp in effective_exposures:
        if exp.weight_of_portfolio <= single_stock_warn:
            continue
        sources: list[str] = []
        if exp.direct_value > 0:
            sources.append(f"direct: ${exp.direct_value:,.0f}")
        for etf, val in exp.etf_contributions.items():
            sources.append(f"via {etf}: ${val:,.0f}")
        alerts.append(
            ConcentrationAlert(
                alert_type="single_stock",
                entity=f"{exp.symbol} ({exp.name})",
                weight=exp.weight_of_portfolio,
                threshold=single_stock_warn,
                message=(
                    f"{exp.symbol} is {exp.weight_of_portfolio:.1%} of portfolio "
                    f"(${exp.total_value:,.0f}). Sources: {', '.join(sources)}"
                ),
            )
        )

    # Sector concentration
    sector_totals: dict[str, float] = {}
    for pos in portfolio.positions:
        if pos.symbol in portfolio.etf_info:
            etf = portfolio.etf_info[pos.symbol]
            pos_value = float(pos.market_value)
            for sector, weight in etf.sector_weights.items():
                sector_totals[sector] = sector_totals.get(sector, 0.0) + pos_value * weight

    for sector, value in sector_totals.items():
        weight = value / total if total > 0 else 0.0
        if weight > sector_warn:
            alerts.append(
                ConcentrationAlert(
                    alert_type="sector",
                    entity=sector,
                    weight=weight,
                    threshold=sector_warn,
                    message=f"Sector '{sector}' is {weight:.1%} of portfolio (${value:,.0f})",
                )
            )

    # Top 10 concentration
    top10 = effective_exposures[:10]
    top10_weight = sum(e.weight_of_portfolio for e in top10)
    if top10_weight > top10_warn:
        names = ", ".join(e.symbol for e in top10)
        alerts.append(
            ConcentrationAlert(
                alert_type="top10",
                entity="Top 10 holdings",
                weight=top10_weight,
                threshold=top10_warn,
                message=f"Top 10 stocks are {top10_weight:.1%} of portfolio: {names}",
            )
        )

    return alerts


def compute_sector_breakdown(portfolio: Portfolio) -> dict[str, float]:
    """Return sector -> portfolio percentage."""
    total = float(portfolio.total_value) or 1.0
    sector_values: dict[str, float] = {}
    for pos in portfolio.positions:
        if pos.symbol in portfolio.etf_info:
            etf = portfolio.etf_info[pos.symbol]
            for sector, weight in etf.sector_weights.items():
                sector_values[sector] = sector_values.get(sector, 0.0) + float(pos.market_value) * weight
    return dict(sorted(sector_values.items(), key=lambda x: x[1], reverse=True))
