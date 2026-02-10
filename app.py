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

from portfolio_analyzer.analysis import concentration, fees, lookthrough, overlap
from portfolio_analyzer.cache.store import CacheStore
from portfolio_analyzer.config import load_config
from portfolio_analyzer.fetcher.etf_holdings import fetch_all_etf_info, identify_etfs
from portfolio_analyzer.fetcher.ibkr import load_from_file, parse_xml_bytes
from portfolio_analyzer.models import AssetType, Portfolio

DEMO_FILE = Path("tests/fixtures/sample_flex_response.xml")


def main() -> None:
    st.set_page_config(page_title="IBKR ETF Analyzer", page_icon="\U0001f4ca", layout="wide")
    analyzer_page = st.Page(_analyzer_page, title="IBKR ETF Analyzer", icon="\U0001f4ca", default=True)
    guide_page = st.Page("pages/1_Flex_Query_Setup_Guide.py", title="Flex Query Setup Guide", icon="\U0001f4d6")
    nav = st.navigation([analyzer_page, guide_page])
    nav.run()


def _analyzer_page() -> None:
    st.title("IBKR ETF Analyzer")
    st.caption("ETF look-through, overlap, fees & concentration analysis")

    # --- Sidebar ---
    with st.sidebar:
        st.header("Data Source")
        mode = st.radio("Choose input", ["Upload Flex Query XML", "Try Demo"], label_visibility="collapsed")

        uploaded_file = None
        if mode == "Upload Flex Query XML":
            uploaded_file = st.file_uploader("Upload your IBKR Flex Query XML", type=["xml"])
            st.info("Your data is processed in-memory and never stored on the server.", icon="\U0001f512")

        st.divider()
        st.header("Analysis Options")
        show_exposures = st.checkbox("Exposures (Look-Through)", value=True)
        show_overlap = st.checkbox("ETF Overlap", value=True)
        show_fees = st.checkbox("Fee Alternatives", value=True)
        show_concentration = st.checkbox("Concentration Alerts", value=True)

        top_n = st.slider("Top N exposures", min_value=5, max_value=50, value=20)

    # --- Determine data source ---
    raw_xml: bytes | None = None
    data_key: str | None = None

    if mode == "Upload Flex Query XML":
        if uploaded_file is None:
            st.info("Upload a Flex Query XML file in the sidebar to get started.")
            return
        raw_xml = uploaded_file.getvalue()
        data_key = hashlib.md5(raw_xml).hexdigest()
    else:
        if not DEMO_FILE.exists():
            st.error(f"Demo file not found: {DEMO_FILE}")
            return
        data_key = "demo"

    # --- Pipeline (cached in session state) ---
    if st.session_state.get("data_key") != data_key:
        _run_pipeline(raw_xml, data_key)

    portfolio: Portfolio = st.session_state["portfolio"]
    config = st.session_state["config"]

    # --- Display ---
    _show_portfolio_summary(portfolio)
    _show_positions_table(portfolio)

    if show_exposures:
        _show_exposures(portfolio, top_n)

    if show_overlap:
        _show_overlap(portfolio)

    if show_fees:
        _show_fees(portfolio, config)

    if show_concentration:
        _show_concentration(portfolio, config)


def _run_pipeline(raw_xml: bytes | None, data_key: str) -> None:
    """Execute the full analysis pipeline and cache results in session state."""
    config = load_config()
    cache = CacheStore(config.cache.directory / "etf_cache.db", config.cache.etf_holdings_ttl_days)

    try:
        # Step 1: Parse positions
        if raw_xml is not None:
            positions = parse_xml_bytes(raw_xml)
        else:
            positions = load_from_file(DEMO_FILE)

        if not positions:
            st.error("No positions found in the XML file.")
            st.stop()

        # Step 2: Identify ETFs
        with st.spinner("Identifying ETFs..."):
            stock_symbols = list(
                {p.symbol for p in positions if p.asset_type in (AssetType.STOCK, AssetType.OTHER)}
            )
            etf_map = identify_etfs(stock_symbols)

        for pos in positions:
            if pos.symbol in etf_map:
                pos.asset_type = AssetType.ETF

        # Step 3: Fetch ETF holdings
        with st.spinner("Fetching ETF holdings data..."):
            etf_info = fetch_all_etf_info(etf_map, cache)

        # Step 3b: Apply expense ratio overrides
        for sym, er in config.expense_ratio_overrides.items():
            if sym in etf_info:
                etf_info[sym].expense_ratio = er

        # Step 4: Build portfolio
        total_value = sum(p.market_value for p in positions)
        portfolio = Portfolio(
            positions=positions,
            etf_info=etf_info,
            total_value=total_value,
            report_date=positions[0].report_date if positions else None,
        )

        st.session_state["data_key"] = data_key
        st.session_state["portfolio"] = portfolio
        st.session_state["config"] = config
    finally:
        cache.close()


def _show_portfolio_summary(portfolio: Portfolio) -> None:
    total_fees = fees.compute_total_annual_fees(portfolio)
    etf_count = sum(1 for p in portfolio.positions if p.symbol in portfolio.etf_info)

    st.subheader("Portfolio Summary")
    cols = st.columns(5)
    cols[0].metric("Report Date", str(portfolio.report_date or "N/A"))
    cols[1].metric("Total Value", f"${portfolio.total_value:,.0f}")
    cols[2].metric("Positions", str(len(portfolio.positions)))
    cols[3].metric("ETFs", str(etf_count))
    cols[4].metric("Annual ETF Fees", f"${total_fees:,.2f}")


def _show_positions_table(portfolio: Portfolio) -> None:
    st.subheader("Current Positions")
    rows = []
    for p in sorted(portfolio.positions, key=lambda x: x.market_value, reverse=True):
        rows.append(
            {
                "Symbol": p.symbol,
                "Type": p.asset_type.value,
                "Qty": float(p.quantity),
                "Market Value": float(p.market_value),
                "Cost Basis": float(p.cost_basis),
                "Unrealized P&L": float(p.unrealized_pnl),
                "Currency": p.currency,
            }
        )
    df = pd.DataFrame(rows)
    st.dataframe(
        df,
        column_config={
            "Market Value": st.column_config.NumberColumn(format="dollar"),
            "Cost Basis": st.column_config.NumberColumn(format="dollar"),
            "Unrealized P&L": st.column_config.NumberColumn(format="dollar"),
            "Qty": st.column_config.NumberColumn(format="localized"),
        },
        use_container_width=True,
        hide_index=True,
    )


def _show_exposures(portfolio: Portfolio, top_n: int) -> None:
    st.subheader(f"Top {top_n} Effective Stock Exposures (Look-Through)")
    effective = lookthrough.compute_effective_exposures(portfolio)

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
    effective = lookthrough.compute_effective_exposures(portfolio)

    # Concentration alerts
    st.subheader("Concentration Alerts")
    alerts = concentration.analyze_concentration(
        portfolio,
        effective,
        single_stock_warn=config.analysis.single_stock_warn,
        sector_warn=config.analysis.sector_warn,
        top10_warn=config.analysis.top10_warn,
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
    sector_pcts = concentration.compute_sector_breakdown(portfolio)
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
