from __future__ import annotations

from decimal import Decimal

from portfolio_analyzer.models import (
    AssetClassBreakdown,
    AssetClassBucket,
    AssetClassDetail,
    AssetType,
    ETFInfo,
    Portfolio,
)

# Direct asset type -> bucket mapping
_ASSET_TYPE_BUCKET: dict[AssetType, AssetClassBucket] = {
    AssetType.STOCK: AssetClassBucket.EQUITIES,
    AssetType.RSU: AssetClassBucket.EQUITIES,
    AssetType.BOND: AssetClassBucket.FIXED_INCOME,
    AssetType.SUKUK: AssetClassBucket.FIXED_INCOME,
    AssetType.OPTION: AssetClassBucket.OTHER,
    AssetType.CASH: AssetClassBucket.OTHER,
    AssetType.CRYPTO: AssetClassBucket.OTHER,
    AssetType.MUTUAL_FUND: AssetClassBucket.OTHER,
    AssetType.OTHER: AssetClassBucket.OTHER,
}

# Keywords in ETF category that indicate fixed income
_FI_KEYWORDS = [
    "bond",
    "fixed income",
    "treasury",
    "aggregate",
    "income",
    "govt",
    "government",
    "municipal",
    "corporate bond",
    "high yield",
    "short-term bond",
    "intermediate-term bond",
    "long-term bond",
    "inflation-protected",
    "tips",
]


def _get_ac(ac: dict[str, float], *keys: str) -> float:
    """Look up an asset-class value trying multiple key variants.

    yfinance may return short keys (``"stock"``) or suffixed ones
    (``"stockPosition"``), depending on version and region.
    """
    for k in keys:
        if k in ac:
            return float(ac[k])
    return 0.0


def classify_etf(etf_info: ETFInfo) -> dict[AssetClassBucket, float]:
    """Determine what fraction of an ETF is equities vs fixed income.

    Uses the ``asset_classes`` dict from yfinance when available,
    otherwise falls back to category-string heuristics.
    """
    ac = etf_info.asset_classes

    if ac:
        eq = _get_ac(ac, "stock", "stockPosition")
        fi = (
            _get_ac(ac, "bond", "bondPosition")
            + _get_ac(ac, "preferredStock", "preferredPosition")
        )
        other = max(0.0, 1.0 - eq - fi)

        # Absorb the residual (internal cash buffer, derivatives used for index
        # replication, etc.) into the dominant bucket.  This avoids confusing
        # "Other" splits for fundamentally equity or bond ETFs — the cash a fund
        # holds is an operational artifact, not an asset class the investor chose.
        if eq >= fi:
            eq = min(1.0, eq + other)
        else:
            fi = min(1.0, fi + other)

        return {
            AssetClassBucket.EQUITIES: eq,
            AssetClassBucket.FIXED_INCOME: fi,
            AssetClassBucket.OTHER: 0.0,
        }

    # Fallback: use category string
    if etf_info.category:
        cat_lower = etf_info.category.lower()
        if any(kw in cat_lower for kw in _FI_KEYWORDS):
            return {
                AssetClassBucket.EQUITIES: 0.0,
                AssetClassBucket.FIXED_INCOME: 1.0,
                AssetClassBucket.OTHER: 0.0,
            }

    # Default: treat unknown ETFs as equity
    return {
        AssetClassBucket.EQUITIES: 1.0,
        AssetClassBucket.FIXED_INCOME: 0.0,
        AssetClassBucket.OTHER: 0.0,
    }


def compute_asset_class_breakdown(
    portfolio: Portfolio,
    overrides: dict[str, str] | None = None,
    currency_rates: dict[str, float] | None = None,
    base_currency: str = "USD",
) -> AssetClassBreakdown:
    """Classify every position into equities vs fixed income buckets.

    *overrides* maps symbol -> ``"equities"`` or ``"fixed_income"`` for
    manual corrections.

    *currency_rates* and *base_currency* are used to convert non-base-currency
    positions so the breakdown totals match ``portfolio.total_value`` (which is
    already in the base currency after consolidation).
    """
    overrides = overrides or {}
    rates = currency_rates or {}

    def _convert(value: Decimal, currency: str) -> Decimal:
        """Convert *value* to the base currency using *rates*."""
        if currency == base_currency or not rates:
            return value
        rate = rates.get(currency)
        if rate is None:
            raise ValueError(
                f"No exchange rate configured for {currency}. "
                f"Add it to config.yaml under currency.rates."
            )
        return value * Decimal(str(rate))

    eq_total = Decimal(0)
    fi_total = Decimal(0)
    ot_total = Decimal(0)
    details: list[AssetClassDetail] = []

    for pos in portfolio.positions:
        mv = _convert(pos.market_value, pos.currency)

        # Check for manual override first
        override = overrides.get(pos.symbol)
        if override:
            eq_val, fi_val, ot_val = _apply_override(override, mv)
        elif pos.asset_type == AssetType.ETF and pos.symbol in portfolio.etf_info:
            fracs = classify_etf(portfolio.etf_info[pos.symbol])
            eq_val = mv * Decimal(str(fracs.get(AssetClassBucket.EQUITIES, 0.0)))
            fi_val = mv * Decimal(str(fracs.get(AssetClassBucket.FIXED_INCOME, 0.0)))
            ot_val = mv * Decimal(str(fracs.get(AssetClassBucket.OTHER, 0.0)))
        else:
            bucket = _ASSET_TYPE_BUCKET.get(pos.asset_type, AssetClassBucket.OTHER)
            eq_val = mv if bucket == AssetClassBucket.EQUITIES else Decimal(0)
            fi_val = mv if bucket == AssetClassBucket.FIXED_INCOME else Decimal(0)
            ot_val = mv if bucket == AssetClassBucket.OTHER else Decimal(0)

        eq_total += eq_val
        fi_total += fi_val
        ot_total += ot_val

        details.append(
            AssetClassDetail(
                symbol=pos.symbol,
                source=pos.source,
                asset_type=pos.asset_type.value,
                market_value=mv,
                equities_portion=eq_val,
                fixed_income_portion=fi_val,
                other_portion=ot_val,
            )
        )

    grand = float(eq_total + fi_total + ot_total) or 1.0
    return AssetClassBreakdown(
        equities_value=eq_total,
        equities_weight=float(eq_total) / grand,
        fixed_income_value=fi_total,
        fixed_income_weight=float(fi_total) / grand,
        other_value=ot_total,
        other_weight=float(ot_total) / grand,
        details=details,
    )


def _apply_override(
    override: str, market_value: Decimal
) -> tuple[Decimal, Decimal, Decimal]:
    """Apply a manual asset-class override."""
    if override == "equities":
        return market_value, Decimal(0), Decimal(0)
    if override == "fixed_income":
        return Decimal(0), market_value, Decimal(0)
    return Decimal(0), Decimal(0), market_value
