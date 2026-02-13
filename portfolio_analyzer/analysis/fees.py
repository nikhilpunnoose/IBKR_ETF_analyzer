from __future__ import annotations

from decimal import Decimal

from portfolio_analyzer.models import FeeAlternative, Portfolio


def analyze_fees(
    portfolio: Portfolio,
    fee_alternatives: dict[str, list[dict]] | None = None,
) -> list[FeeAlternative]:
    """For each ETF, suggest cheaper alternatives in the same category."""
    alternatives: list[FeeAlternative] = []
    alt_map = fee_alternatives or {}

    for pos in portfolio.positions:
        if pos.symbol not in portfolio.etf_info:
            continue
        info = portfolio.etf_info[pos.symbol]
        if info.expense_ratio is None or info.category is None:
            continue

        category_alts = alt_map.get(info.category, [])
        for alt in category_alts:
            alt_sym = alt["symbol"]
            alt_er = alt["expense_ratio"]
            if alt_sym == pos.symbol:
                continue
            if alt_er >= info.expense_ratio:
                continue

            savings = pos.market_value * Decimal(str(info.expense_ratio - alt_er))
            alternatives.append(
                FeeAlternative(
                    current_etf=pos.symbol,
                    current_expense_ratio=info.expense_ratio,
                    alternative_etf=alt_sym,
                    alternative_expense_ratio=alt_er,
                    alternative_category=info.category,
                    estimated_annual_savings=savings,
                )
            )

    return sorted(alternatives, key=lambda a: a.estimated_annual_savings, reverse=True)


def compute_total_annual_fees(portfolio: Portfolio) -> Decimal:
    """Compute the total weighted annual fee across all ETF positions."""
    total = Decimal(0)
    for pos in portfolio.positions:
        if pos.symbol in portfolio.etf_info:
            er = portfolio.etf_info[pos.symbol].expense_ratio
            if er is not None:
                total += pos.market_value * Decimal(str(er))
    return total
