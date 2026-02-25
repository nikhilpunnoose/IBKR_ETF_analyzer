"""Streamlit web app for Portfolio Analyzer.

Replaces cli.py (orchestration) and display/tables.py (presentation) for the web.
All analysis modules are reused unchanged.
"""

from __future__ import annotations

import hashlib
from decimal import Decimal
from pathlib import Path

import pandas as pd
import streamlit as st

from auth import (
    auth_available,
    get_login_url,
    get_user,
    get_user_id,
    handle_oauth_callback,
    has_ibkr_credentials,
    is_authenticated,
    load_ibkr_credentials,
    logout,
    restore_session,
)
from portfolio_analyzer.analysis import concentration, fees, lookthrough, overlap
from portfolio_analyzer.analysis import asset_class
from portfolio_analyzer.cache.store import CacheStore
from portfolio_analyzer.config import load_config
from portfolio_analyzer.fetcher.consolidate import build_consolidated_portfolio
from portfolio_analyzer.fetcher.etf_holdings import fetch_all_etf_info, identify_etfs
from portfolio_analyzer.fetcher.ibkr import fetch_positions, load_from_file, parse_xml_bytes
from portfolio_analyzer.fetcher.manual import load_manual_positions
from portfolio_analyzer.models import AssetType, Portfolio

DEMO_FILE = Path("tests/fixtures/sample_flex_response.xml")


_SOURCE_LABELS: dict[str, str] = {
    "enbd": "Manual Asset",
    "equateplus": "Manual RSU",
    "etoro": "eToro",
    "ibkr": "IBKR",
}


def _source_label(source: str) -> str:
    """Return a human-readable label for a position source code."""
    return _SOURCE_LABELS.get(source, source.upper())


def main() -> None:
    st.set_page_config(page_title="Portfolio Analyzer", page_icon="\U0001f4ca", layout="wide")

    # Handle OAuth callback before anything else
    use_auth = auth_available()
    if use_auth:
        if handle_oauth_callback():
            st.rerun()
        restore_session()

    # Build page list
    pages = [
        st.Page(_analyzer_page, title="Portfolio Analyzer", icon="\U0001f4ca", default=True),
        st.Page("pages/1_Flex_Query_Setup_Guide.py", title="Flex Query Setup Guide", icon="\U0001f4d6"),
        st.Page("pages/3_Manual_Positions.py", title="Manual Positions", icon="\u270f\ufe0f"),
    ]
    if use_auth and is_authenticated():
        pages.append(
            st.Page("pages/2_Account_Settings.py", title="Account Settings", icon="\u2699\ufe0f")
        )

    # Auth UI in sidebar (only if Supabase is configured)
    if use_auth:
        with st.sidebar:
            if is_authenticated():
                user = get_user()
                st.caption(f"Signed in as {user.email}")
                if st.button("Sign Out"):
                    logout()
                    st.rerun()
            else:
                login_url = get_login_url()
                st.link_button("Sign in with Google", login_url)

    nav = st.navigation(pages)
    nav.run()


def _analyzer_page() -> None:
    st.title("Portfolio Analyzer")
    st.caption("Multi-broker ETF look-through, overlap, fees, concentration & asset class analysis")

    # --- Sidebar ---
    with st.sidebar:
        use_auth = auth_available()
        authenticated = use_auth and is_authenticated()
        user_id = get_user_id() if authenticated else None

        # --- Data Sources ---
        st.header("Data Sources")

        # IBKR source
        with st.expander("IBKR", expanded=True):
            show_ibkr_live = authenticated and user_id and has_ibkr_credentials(user_id)
            ibkr_options = []
            if show_ibkr_live:
                ibkr_options.append("Load from IBKR")
            ibkr_options.extend(["Upload XML", "Demo", "None"])
            ibkr_mode = st.radio(
                "IBKR source", ibkr_options, label_visibility="collapsed",
                index=len(ibkr_options) - 2 if "Demo" in ibkr_options else 0,
            )

            ibkr_uploaded = None
            if ibkr_mode == "Upload XML":
                ibkr_uploaded = st.file_uploader("IBKR Flex Query XML", type=["xml"])
            elif ibkr_mode == "Load from IBKR":
                if st.button("Refresh from IBKR"):
                    st.session_state.pop("data_key", None)
                    st.rerun()

        # eToro source
        with st.expander("eToro"):
            include_etoro = st.checkbox("Include eToro positions")
            etoro_uploaded = None
            if include_etoro:
                etoro_uploaded = st.file_uploader(
                    "eToro Account Statement", type=["xlsx", "xls"],
                )

        # Manual sources
        with st.expander("Manual Positions"):
            include_enbd = st.checkbox("Include manual asset positions")
            include_equateplus = st.checkbox("Include manual RSU positions")
            if include_enbd or include_equateplus:
                st.caption("Manage positions on the [Manual Positions](/Manual_Positions) page")

        st.divider()
        st.header("Analysis Options")
        show_exposures = st.checkbox("Exposures (Look-Through)", value=True)
        show_overlap = st.checkbox("ETF Overlap", value=True)
        show_fees = st.checkbox("Fee Alternatives", value=True)
        show_concentration = st.checkbox("Concentration Alerts", value=True)
        show_asset_class = st.checkbox("Asset Class Breakdown", value=True)

        top_n = st.slider("Top N exposures", min_value=5, max_value=50, value=20)

    # --- Gather positions from all enabled sources ---
    all_positions = []
    data_key_parts = []

    # IBKR
    ibkr_raw_xml: bytes | None = None
    ibkr_prefetched = None
    if ibkr_mode == "Load from IBKR":
        data_key_parts.append(f"ibkr_live_{user_id}")
        if st.session_state.get("data_key") is None or "ibkr_live" not in str(st.session_state.get("data_key", "")):
            creds = load_ibkr_credentials(user_id)
            if not creds:
                st.error("Could not load saved credentials. Please update them in Account Settings.")
                return
            token, query_id = creds
            with st.spinner("Fetching positions from IBKR..."):
                try:
                    ibkr_prefetched = fetch_positions(token, query_id)
                except Exception as e:
                    st.error(f"Failed to fetch from IBKR: {e}")
                    return
    elif ibkr_mode == "Upload XML":
        if ibkr_uploaded is None:
            if not include_etoro and not include_enbd and not include_equateplus:
                st.info("Upload an IBKR Flex Query XML file in the sidebar to get started.")
                return
        else:
            ibkr_raw_xml = ibkr_uploaded.getvalue()
            data_key_parts.append(hashlib.md5(ibkr_raw_xml).hexdigest())
    elif ibkr_mode == "Demo":
        if not DEMO_FILE.exists():
            st.error(f"Demo file not found: {DEMO_FILE}")
            return
        data_key_parts.append("demo")
    # ibkr_mode == "None" -> skip

    # eToro
    etoro_raw: bytes | None = None
    if include_etoro and etoro_uploaded is not None:
        etoro_raw = etoro_uploaded.getvalue()
        data_key_parts.append(f"etoro_{hashlib.md5(etoro_raw).hexdigest()}")
    elif include_etoro:
        data_key_parts.append("etoro_pending")

    # Manual sources
    if include_enbd:
        data_key_parts.append("enbd")
    if include_equateplus:
        data_key_parts.append("equateplus")

    if not data_key_parts:
        st.info("Select at least one data source in the sidebar to get started.")
        return

    # Skip if only pending eToro upload
    if data_key_parts == ["etoro_pending"]:
        st.info("Upload an eToro account statement in the sidebar to get started.")
        return

    data_key = "|".join(sorted(data_key_parts))

    # --- Pipeline (cached in session state) ---
    if st.session_state.get("data_key") != data_key:
        _run_pipeline(
            ibkr_raw_xml=ibkr_raw_xml,
            ibkr_prefetched=ibkr_prefetched,
            ibkr_mode=ibkr_mode,
            etoro_raw=etoro_raw,
            include_enbd=include_enbd,
            include_equateplus=include_equateplus,
            data_key=data_key,
            user_id=user_id,
        )

    portfolio: Portfolio = st.session_state["portfolio"]
    config = st.session_state["config"]

    # --- Display ---
    _show_portfolio_summary(portfolio)
    _show_positions_table(portfolio, config)

    if show_asset_class:
        _show_asset_class(portfolio, config)

    if show_exposures:
        _show_exposures(portfolio, top_n, config)

    if show_overlap:
        _show_overlap(portfolio)

    if show_fees:
        _show_fees(portfolio, config)

    if show_concentration:
        _show_concentration(portfolio, config)


def _run_pipeline(
    *,
    ibkr_raw_xml: bytes | None,
    ibkr_prefetched: list | None,
    ibkr_mode: str,
    etoro_raw: bytes | None,
    include_enbd: bool,
    include_equateplus: bool,
    data_key: str,
    user_id: str | None,
) -> None:
    """Execute the full analysis pipeline and cache results in session state."""
    config = load_config()
    cache = CacheStore(config.cache.directory / "etf_cache.db", config.cache.etf_holdings_ttl_days)

    try:
        sources: dict[str, list] = {}

        # Step 1a: IBKR positions
        if ibkr_prefetched is not None:
            sources["ibkr"] = ibkr_prefetched
        elif ibkr_raw_xml is not None:
            sources["ibkr"] = parse_xml_bytes(ibkr_raw_xml)
        elif ibkr_mode == "Demo":
            sources["ibkr"] = load_from_file(DEMO_FILE)

        # Step 1b: eToro positions
        if etoro_raw is not None:
            from portfolio_analyzer.fetcher.etoro import parse_etoro_bytes
            sources["etoro"] = parse_etoro_bytes(etoro_raw, "upload.xlsx")

        # Step 1c: Manual positions
        if include_enbd:
            enbd = load_manual_positions(user_id, "enbd")
            if enbd:
                sources["enbd"] = enbd

        if include_equateplus:
            eq = load_manual_positions(user_id, "equateplus")
            if eq:
                sources["equateplus"] = eq

        # Merge all positions
        all_positions = []
        for pos_list in sources.values():
            all_positions.extend(pos_list)

        if not all_positions:
            st.error("No positions found from any source.")
            st.stop()

        # Step 2: Identify ETFs (from STOCK/OTHER positions that yfinance classifies as ETF)
        with st.spinner("Identifying ETFs..."):
            stock_symbols = list(
                {p.symbol for p in all_positions if p.asset_type in (AssetType.STOCK, AssetType.OTHER)}
            )
            etf_map = identify_etfs(stock_symbols)

        for pos in all_positions:
            if pos.symbol in etf_map:
                pos.asset_type = AssetType.ETF

        # Also include positions the user explicitly declared as ETF (e.g. manually
        # added CSPX from ENBD).  They skip the identification step but still need
        # their holdings fetched so look-through and decomposition work correctly.
        for pos in all_positions:
            if pos.asset_type == AssetType.ETF and pos.symbol not in etf_map:
                etf_map[pos.symbol] = pos.symbol

        # Step 3: Fetch ETF holdings
        with st.spinner("Fetching ETF holdings data..."):
            etf_info = fetch_all_etf_info(etf_map, cache)

        # Step 3b: Apply expense ratio overrides
        for sym, er in config.expense_ratio_overrides.items():
            if sym in etf_info:
                etf_info[sym].expense_ratio = er

        # Step 4: Build consolidated portfolio
        portfolio = build_consolidated_portfolio(
            sources=sources,
            etf_info=etf_info,
            currency_rates=config.currency.rates,
            base_currency=config.currency.base,
            report_date=all_positions[0].report_date if all_positions else None,
        )

        st.session_state["data_key"] = data_key
        st.session_state["portfolio"] = portfolio
        st.session_state["config"] = config
    finally:
        cache.close()


def _show_portfolio_summary(portfolio: Portfolio) -> None:
    total_fees = fees.compute_total_annual_fees(portfolio)
    etf_count = sum(1 for p in portfolio.positions if p.symbol in portfolio.etf_info)
    sources = sorted(set(p.source for p in portfolio.positions))

    st.subheader("Portfolio Summary")
    cols = st.columns(6)
    cols[0].metric("Report Date", str(portfolio.report_date or "N/A"))
    cols[1].metric("Total Value", f"${portfolio.total_value:,.0f}")
    cols[2].metric("Positions", str(len(portfolio.positions)))
    cols[3].metric("ETFs", str(etf_count))
    cols[4].metric("Annual ETF Fees", f"${total_fees:,.2f}")
    cols[5].metric("Sources", ", ".join(_source_label(s) for s in sources))


def _show_positions_table(portfolio: Portfolio, config) -> None:
    st.subheader("Current Positions")
    sources = set(p.source for p in portfolio.positions)
    multi_source = len(sources) > 1
    rates = config.currency.rates
    base = config.currency.base

    def _to_base(value, currency):
        if currency == base or not rates:
            return float(value)
        return float(value) * rates.get(currency, 1.0)

    rows = []
    for p in portfolio.positions:
        usd_val = _to_base(p.market_value, p.currency)
        row = {"Symbol": p.symbol}
        if multi_source:
            row["Source"] = _source_label(p.source)
        row.update(
            {
                "Type": p.asset_type.value,
                "Qty": float(p.quantity),
                "Market Value": float(p.market_value),
                "Currency": p.currency,
                f"Value ({base})": usd_val,
                "Cost Basis": float(p.cost_basis),
                "Unrealized P&L": float(p.unrealized_pnl),
            }
        )
        rows.append(row)

    # Sort by base-currency value so mixed-currency portfolios rank correctly
    rows.sort(key=lambda r: r[f"Value ({base})"], reverse=True)
    df = pd.DataFrame(rows)
    st.dataframe(
        df,
        column_config={
            # Market Value is in native currency — no dollar sign
            "Market Value": st.column_config.NumberColumn(format="localized"),
            "Cost Basis": st.column_config.NumberColumn(format="localized"),
            "Unrealized P&L": st.column_config.NumberColumn(format="localized"),
            "Qty": st.column_config.NumberColumn(format="localized"),
            # Value (USD) is always in base currency — dollar sign is correct
            f"Value ({base})": st.column_config.NumberColumn(format="dollar"),
        },
        use_container_width=True,
        hide_index=True,
    )


def _show_asset_class(portfolio: Portfolio, config) -> None:
    st.subheader("Asset Class Breakdown")
    breakdown = asset_class.compute_asset_class_breakdown(
        portfolio,
        overrides=config.asset_class_overrides,
        currency_rates=config.currency.rates,
        base_currency=config.currency.base,
    )

    # Summary metrics
    cols = st.columns(3)
    cols[0].metric(
        "Equities",
        f"${breakdown.equities_value:,.0f}",
        f"{breakdown.equities_weight:.1%}",
    )
    cols[1].metric(
        "Fixed Income",
        f"${breakdown.fixed_income_value:,.0f}",
        f"{breakdown.fixed_income_weight:.1%}",
    )
    cols[2].metric(
        "Other",
        f"${breakdown.other_value:,.0f}",
        f"{breakdown.other_weight:.1%}",
    )

    # Pie chart data
    chart_data = {}
    if breakdown.equities_value:
        chart_data["Equities"] = float(breakdown.equities_value)
    if breakdown.fixed_income_value:
        chart_data["Fixed Income"] = float(breakdown.fixed_income_value)
    if breakdown.other_value:
        chart_data["Other"] = float(breakdown.other_value)

    if chart_data:
        chart_df = pd.DataFrame(
            {"Asset Class": list(chart_data.keys()), "Value ($)": list(chart_data.values())}
        )
        chart_df = chart_df.set_index("Asset Class")
        st.bar_chart(chart_df)

    # Detail table
    if breakdown.details:
        with st.expander("Position-level detail"):
            detail_rows = []
            for d in sorted(breakdown.details, key=lambda x: x.market_value, reverse=True):
                detail_rows.append(
                    {
                        "Symbol": d.symbol,
                        "Source": _source_label(d.source),
                        "Type": d.asset_type,
                        "Market Value": float(d.market_value),
                        "Equities": float(d.equities_portion),
                        "Fixed Income": float(d.fixed_income_portion),
                        "Other": float(d.other_portion),
                    }
                )
            detail_df = pd.DataFrame(detail_rows)
            st.dataframe(
                detail_df,
                column_config={
                    "Market Value": st.column_config.NumberColumn(format="dollar"),
                    "Equities": st.column_config.NumberColumn(format="dollar"),
                    "Fixed Income": st.column_config.NumberColumn(format="dollar"),
                    "Other": st.column_config.NumberColumn(format="dollar"),
                },
                use_container_width=True,
                hide_index=True,
            )


def _show_exposures(portfolio: Portfolio, top_n: int, config) -> None:
    st.subheader(f"Top {top_n} Effective Stock Exposures (Look-Through)")
    effective = lookthrough.compute_effective_exposures(
        portfolio,
        currency_rates=config.currency.rates,
        base_currency=config.currency.base,
    )

    rows = []
    for i, exp in enumerate(effective[:top_n], 1):
        etf_total = sum(exp.etf_contributions.values(), Decimal(0))
        etf_sources = ", ".join(f"{etf}(${v:,.0f})" for etf, v in exp.etf_contributions.items())
        rows.append(
            {
                "#": i,
                "Stock": exp.symbol,
                "Total Value": float(exp.total_value),
                "% Portfolio": exp.weight_of_portfolio * 100,
                "Direct": float(exp.direct_value) if exp.direct_value else None,
                "Via ETFs": float(etf_total) if etf_total else None,
                "ETF Sources": etf_sources or "-",
            }
        )
    df = pd.DataFrame(rows)
    st.dataframe(
        df,
        column_config={
            "Total Value": st.column_config.NumberColumn(format="dollar"),
            "% Portfolio": st.column_config.NumberColumn(format="%.2f%%"),
            "Direct": st.column_config.NumberColumn(format="dollar"),
            "Via ETFs": st.column_config.NumberColumn(format="dollar"),
        },
        use_container_width=True,
        hide_index=True,
    )


def _show_overlap(portfolio: Portfolio) -> None:
    st.subheader("ETF Holding Overlap")
    pairs = overlap.compute_overlap(portfolio)

    if not pairs:
        st.info("No ETF overlap detected.")
        return

    rows = []
    for p in pairs:
        preview = ", ".join(p.shared_holdings[:5])
        if len(p.shared_holdings) > 5:
            preview += "..."
        rows.append(
            {
                "ETF A": p.etf_a,
                "ETF B": p.etf_b,
                "Shared": len(p.shared_holdings),
                "Overlap Coeff": p.overlap_coefficient,
                "Overlap in A": p.overlap_weight_a * 100,
                "Overlap in B": p.overlap_weight_b * 100,
                "Shared Stocks": preview,
            }
        )
    df = pd.DataFrame(rows)
    st.dataframe(
        df,
        column_config={
            "Overlap Coeff": st.column_config.NumberColumn(format="%.2f"),
            "Overlap in A": st.column_config.NumberColumn(format="%.1f%%"),
            "Overlap in B": st.column_config.NumberColumn(format="%.1f%%"),
        },
        use_container_width=True,
        hide_index=True,
    )


def _show_fees(portfolio: Portfolio, config) -> None:
    st.subheader("Fee Optimization Opportunities")
    alternatives = fees.analyze_fees(portfolio, config.analysis.fee_alternatives)

    if not alternatives:
        st.info("No cheaper ETF alternatives found.")
        return

    rows = []
    for a in alternatives:
        rows.append(
            {
                "Current ETF": a.current_etf,
                "ER": a.current_expense_ratio,
                "Alternative": a.alternative_etf,
                "Alt ER": a.alternative_expense_ratio,
                "Est. Annual Savings": float(a.estimated_annual_savings),
                "Category": a.alternative_category,
            }
        )
    df = pd.DataFrame(rows)
    st.dataframe(
        df,
        column_config={
            "ER": st.column_config.NumberColumn(format="%.4f"),
            "Alt ER": st.column_config.NumberColumn(format="%.4f"),
            "Est. Annual Savings": st.column_config.NumberColumn(format="dollar"),
        },
        use_container_width=True,
        hide_index=True,
    )


def _show_concentration(portfolio: Portfolio, config) -> None:
    effective = lookthrough.compute_effective_exposures(
        portfolio,
        currency_rates=config.currency.rates,
        base_currency=config.currency.base,
    )

    # Concentration alerts
    st.subheader("Concentration Alerts")
    alerts = concentration.analyze_concentration(
        portfolio,
        effective,
        single_stock_warn=config.analysis.single_stock_warn,
        sector_warn=config.analysis.sector_warn,
        top10_warn=config.analysis.top10_warn,
        currency_rates=config.currency.rates,
        base_currency=config.currency.base,
    )

    if not alerts:
        st.success("No concentration alerts.")
    else:
        for alert in alerts:
            if alert.weight < alert.threshold * 1.5:
                st.warning(f"**[{alert.alert_type.upper()}] {alert.entity}**\n\n{alert.message}")
            else:
                st.error(f"**[{alert.alert_type.upper()}] {alert.entity}**\n\n{alert.message}")

    # Sector breakdown
    st.subheader("Sector Breakdown")
    sector_pcts = concentration.compute_sector_breakdown(
        portfolio,
        currency_rates=config.currency.rates,
        base_currency=config.currency.base,
    )
    if not sector_pcts:
        st.info("No sector data available.")
        return

    total_value = float(portfolio.total_value) or 1.0
    rows = []
    for sector, value in sector_pcts.items():
        pct = value / total_value * 100
        rows.append({"Sector": sector, "Value": value, "Weight": pct})

    df = pd.DataFrame(rows)
    st.dataframe(
        df,
        column_config={
            "Value": st.column_config.NumberColumn(format="dollar"),
            "Weight": st.column_config.NumberColumn(format="%.1f%%"),
        },
        use_container_width=True,
        hide_index=True,
    )

    # Bar chart
    chart_df = pd.DataFrame({"Sector": list(sector_pcts.keys()), "Value ($)": list(sector_pcts.values())})
    chart_df = chart_df.set_index("Sector")
    st.bar_chart(chart_df)


if __name__ == "__main__":
    main()
