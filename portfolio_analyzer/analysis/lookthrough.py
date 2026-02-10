from __future__ import annotations

from decimal import Decimal

from portfolio_analyzer.models import AssetType, EffectiveExposure, Portfolio


def compute_effective_exposures(portfolio: Portfolio) -> list[EffectiveExposure]:
    """Decompose ETF positions into underlying stock exposures and merge with direct holdings."""
    exposures: dict[str, EffectiveExposure] = {}

    # Direct stock holdings
    for pos in portfolio.positions:
        if pos.asset_type == AssetType.STOCK:
            sym = pos.symbol
            if sym not in exposures:
                exposures[sym] = EffectiveExposure(
                    symbol=sym,
                    name=pos.description,
                    total_value=Decimal(0),
                    direct_value=Decimal(0),
                )
            exposures[sym].direct_value += pos.market_value
            exposures[sym].total_value += pos.market_value

    # Look through ETFs
    for pos in portfolio.positions:
        if pos.asset_type != AssetType.ETF or pos.symbol not in portfolio.etf_info:
            continue
        etf = portfolio.etf_info[pos.symbol]
        etf_value = pos.market_value
        for holding in etf.top_holdings:
            sym = holding.symbol
            effective_value = etf_value * Decimal(str(holding.weight))
            if sym not in exposures:
                exposures[sym] = EffectiveExposure(
                    symbol=sym,
                    name=holding.name,
                    total_value=Decimal(0),
                    direct_value=Decimal(0),
                )
            exposures[sym].total_value += effective_value
            exposures[sym].etf_contributions[pos.symbol] = (
                exposures[sym].etf_contributions.get(pos.symbol, Decimal(0)) + effective_value
            )

    # Compute portfolio weight percentages
    total = float(portfolio.total_value) if portfolio.total_value else 1.0
    for exp in exposures.values():
        exp.weight_of_portfolio = float(exp.total_value) / total

    return sorted(exposures.values(), key=lambda e: e.total_value, reverse=True)
