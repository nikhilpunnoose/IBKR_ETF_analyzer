from __future__ import annotations

import logging
from datetime import date

import yfinance as yf

from portfolio_analyzer.cache.store import CacheStore
from portfolio_analyzer.models import ETFHolding, ETFInfo

logger = logging.getLogger(__name__)

# Common exchange suffixes for European-listed ETFs
_EXCHANGE_SUFFIXES = ["", ".L", ".AS", ".DE", ".PA", ".MI", ".SW", ".IR"]


def _resolve_yf_symbol(symbol: str) -> tuple[str, str | None]:
    """Try the plain symbol and common exchange suffixes.

    Returns (original_symbol, yfinance_symbol) where yfinance_symbol is the
    one that worked, or None if nothing matched as an ETF.
    """
    # If the plain symbol is already a stock/equity, skip suffix hunting.
    # This prevents ghost exchange listings (e.g. AAPL.L) from causing false
    # positives when yfinance incorrectly tags them as ETF.
    try:
        ticker = yf.Ticker(symbol)
        qt = (ticker.fast_info.get("quoteType", "") or "").upper()
        if qt in ("EQUITY", "STOCK"):
            return symbol, None
    except Exception:
        pass

    for suffix in _EXCHANGE_SUFFIXES:
        yf_sym = symbol + suffix
        try:
            ticker = yf.Ticker(yf_sym)
            qt = (ticker.fast_info.get("quoteType", "") or "").upper()
            if qt == "ETF":
                if suffix:
                    logger.info("Resolved %s -> %s", symbol, yf_sym)
                return symbol, yf_sym
        except Exception:
            continue
    return symbol, None


def identify_etfs(symbols: list[str]) -> dict[str, str]:
    """From a list of symbols, return a mapping of IBKR symbol -> yfinance symbol for ETFs."""
    etf_map: dict[str, str] = {}
    for sym in symbols:
        _, yf_sym = _resolve_yf_symbol(sym)
        if yf_sym is not None:
            etf_map[sym] = yf_sym
    return etf_map


def fetch_etf_info(ibkr_symbol: str, yf_symbol: str) -> ETFInfo | None:
    """Fetch ETF metadata and holdings from yfinance."""
    try:
        ticker = yf.Ticker(yf_symbol)
        fd = ticker.funds_data

        # Top holdings
        holdings: list[ETFHolding] = []
        try:
            th = fd.top_holdings
            if th is not None and not th.empty:
                for sym, row in th.iterrows():
                    holdings.append(
                        ETFHolding(
                            symbol=str(sym),
                            name=str(row.get("Name", "")),
                            weight=float(row.get("Holding Percent", 0)),
                        )
                    )
        except Exception as exc:
            logger.debug("Could not get top_holdings for %s: %s", yf_symbol, exc)

        # Sector weights
        sector_weights: dict[str, float] = {}
        try:
            sw = fd.sector_weightings
            if sw:
                if isinstance(sw, dict):
                    sector_weights = {k: float(v) for k, v in sw.items()}
                elif isinstance(sw, list):
                    for entry in sw:
                        if isinstance(entry, dict):
                            sector_weights.update({k: float(v) for k, v in entry.items()})
        except Exception as exc:
            logger.debug("Could not get sector_weightings for %s: %s", yf_symbol, exc)

        # Expense ratio — try multiple keys since yfinance varies by region
        expense_ratio: float | None = None
        try:
            fo = fd.fund_operations
            if fo is not None and not fo.empty:
                for key in ["Annual Report Expense Ratio (net)", "Annual Report Expense Ratio"]:
                    try:
                        val = float(fo.loc[key].iloc[0])
                        if val > 0:
                            expense_ratio = val
                            break
                    except (KeyError, IndexError):
                        continue
        except Exception:
            pass
        if not expense_ratio:
            try:
                info = ticker.info
                for key in ["annualReportExpenseRatio", "totalExpenseRatio", "expenseRatio"]:
                    val = info.get(key)
                    if val is not None and val > 0:
                        expense_ratio = float(val)
                        break
            except Exception:
                pass

        # Category and family
        category: str | None = None
        family: str | None = None
        try:
            overview = fd.fund_overview
            if isinstance(overview, dict):
                category = overview.get("categoryName")
                family = overview.get("family")
        except Exception:
            pass
        if not category or not family:
            try:
                info = ticker.info
                category = category or info.get("category")
                family = family or info.get("fundFamily")
            except Exception:
                pass

        # Asset classes
        asset_classes: dict[str, float] = {}
        try:
            ac = fd.asset_classes
            if isinstance(ac, dict):
                asset_classes = {k: float(v) for k, v in ac.items()}
        except Exception:
            pass

        name = ""
        try:
            name = ticker.info.get("shortName", yf_symbol) or yf_symbol
        except Exception:
            name = yf_symbol

        return ETFInfo(
            symbol=ibkr_symbol,
            name=name,
            expense_ratio=expense_ratio,
            category=category,
            family=family,
            top_holdings=holdings,
            sector_weights=sector_weights,
            asset_classes=asset_classes,
            total_net_assets=None,
            fetched_at=date.today(),
        )
    except Exception as exc:
        logger.warning("Failed to fetch ETF data for %s (%s): %s", ibkr_symbol, yf_symbol, exc)
        return None


def fetch_all_etf_info(etf_map: dict[str, str], cache: CacheStore) -> dict[str, ETFInfo]:
    """Fetch ETF info for all symbols, using cache where fresh.

    etf_map: IBKR symbol -> yfinance symbol
    """
    result: dict[str, ETFInfo] = {}
    for ibkr_sym, yf_sym in etf_map.items():
        cached = cache.get_etf_info(ibkr_sym)
        if cached is not None:
            logger.info("Using cached data for %s", ibkr_sym)
            result[ibkr_sym] = cached
            continue
        info = fetch_etf_info(ibkr_sym, yf_sym)
        if info is not None:
            cache.put_etf_info(ibkr_sym, info)
            result[ibkr_sym] = info
    return result
