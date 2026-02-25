from __future__ import annotations

from decimal import Decimal

from portfolio_analyzer.models import AssetType, EffectiveExposure, Portfolio


def compute_effective_exposures(
    portfolio: Portfolio,
    currency_rates: dict[str, float] | None = None,
    base_currency: str = "USD",
) -> list[EffectiveExposure]:
    """Decompose ETF positions into underlying stock exposures and merge with direct holdings.

    All values stored in ``EffectiveExposure`` are converted to *base_currency*
    so that ``weight_of_portfolio`` (divided by ``portfolio.total_value``, which is
    already in base currency) is meaningful when the portfolio contains non-base
    currency positions.
    """
    rates = currency_rates or {}

    def _convert(value: Decimal, currency: str) -> Decimal:
        if currency == base_currency or not rates:
            return value
        rate = rates.get(currency)
        if rate is None:
            raise ValueError(
                f"No exchange rate configured for {currency}. "
                f"Add it to config.yaml under currency.rates."
            )
        return value * Decimal(str(rate))

    exposures: dict[str, EffectiveExposure] = {}

    # Direct stock and RSU holdings
    for pos in portfolio.positions:
        if pos.asset_type in (AssetType.STOCK, AssetType.RSU):
            sym = pos.symbol
            mv = _convert(pos.market_value, pos.currency)
            if sym not in exposures:
                exposures[sym] = EffectiveExposure(
                    symbol=sym,
                    name=pos.description,
                    total_value=Decimal(0),
                    direct_value=Decimal(0),
                )
            exposures[sym].direct_value += mv
            exposures[sym].total_value += mv

    # Look through ETFs
    for pos in portfolio.positions:
        if pos.asset_type != AssetType.ETF or pos.symbol not in portfolio.etf_info:
            continue
        etf = portfolio.etf_info[pos.symbol]
        etf_value = _convert(pos.market_value, pos.currency)
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
