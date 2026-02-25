from __future__ import annotations

from datetime import date
from decimal import Decimal

from portfolio_analyzer.models import ETFInfo, Portfolio, Position


def to_base_currency(
    value: Decimal, currency: str, rates: dict[str, float], base: str = "USD"
) -> Decimal:
    """Convert a value to the base currency using configured rates."""
    if currency == base:
        return value
    rate = rates.get(currency)
    if rate is None:
        raise ValueError(
            f"No exchange rate configured for {currency}. "
            f"Add it to config.yaml under currency.rates."
        )
    return value * Decimal(str(rate))


def build_consolidated_portfolio(
    sources: dict[str, list[Position]],
    etf_info: dict[str, ETFInfo],
    currency_rates: dict[str, float] | None = None,
    base_currency: str = "USD",
    report_date: date | None = None,
) -> Portfolio:
    """Merge positions from multiple sources into a single Portfolio.

    Each source maps a name (e.g. "ibkr", "etoro") to its position list.
    Positions are NOT deduplicated — the same stock at two brokers remains
    as two separate Position objects.  Analysis modules aggregate by symbol.
    """
    rates = currency_rates or {}
    all_positions: list[Position] = []
    for positions in sources.values():
        all_positions.extend(positions)

    total_value = sum(
        to_base_currency(p.market_value, p.currency, rates, base_currency)
        for p in all_positions
    )

    return Portfolio(
        positions=all_positions,
        etf_info=etf_info,
        total_value=total_value,
        report_date=report_date or date.today(),
    )
