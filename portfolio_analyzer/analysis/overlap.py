from __future__ import annotations

from portfolio_analyzer.models import OverlapPair, Portfolio


def compute_overlap(portfolio: Portfolio) -> list[OverlapPair]:
    """For each pair of ETFs, compute shared holdings and overlap metrics."""
    etf_symbols = list(portfolio.etf_info.keys())
    pairs: list[OverlapPair] = []

    for i, sym_a in enumerate(etf_symbols):
        for sym_b in etf_symbols[i + 1 :]:
            info_a = portfolio.etf_info[sym_a]
            info_b = portfolio.etf_info[sym_b]

            holdings_a = {h.symbol: h.weight for h in info_a.top_holdings}
            holdings_b = {h.symbol: h.weight for h in info_b.top_holdings}

            shared = set(holdings_a) & set(holdings_b)
            if not shared:
                continue

            overlap_weight_a = sum(holdings_a[s] for s in shared)
            overlap_weight_b = sum(holdings_b[s] for s in shared)

            n_min = min(len(holdings_a), len(holdings_b))
            overlap_coeff = len(shared) / n_min if n_min > 0 else 0.0

            pairs.append(
                OverlapPair(
                    etf_a=sym_a,
                    etf_b=sym_b,
                    shared_holdings=sorted(shared),
                    overlap_weight_a=overlap_weight_a,
                    overlap_weight_b=overlap_weight_b,
                    overlap_coefficient=overlap_coeff,
                )
            )

    return sorted(pairs, key=lambda p: p.overlap_coefficient, reverse=True)
