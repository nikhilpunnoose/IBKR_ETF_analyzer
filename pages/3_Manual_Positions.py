"""Manual Positions page — manage manually-entered asset and RSU holdings."""

from __future__ import annotations

import streamlit as st

from portfolio_analyzer.fetcher.manual import (
    add_manual_position,
    delete_manual_position,
    load_manual_positions,
    make_manual_position,
    _load_raw,
)
from portfolio_analyzer.models import AssetType

try:
    from auth import get_user_id, is_authenticated
except Exception:
    def is_authenticated():
        return False
    def get_user_id():
        return None


def _get_user_id() -> str | None:
    try:
        if is_authenticated():
            return get_user_id()
    except Exception:
        pass
    return None


st.title("Manual Positions")
st.caption("Add holdings manually for assets and employee stock grants")

user_id = _get_user_id()

tab_enbd, tab_equate = st.tabs(["Manual Asset Additions", "Manual RSU Additions"])

# ---------- Manual Asset Additions ----------

with tab_enbd:
    st.subheader("Manual Asset Portfolio")
    st.caption("Manually enter your asset holdings (stocks, ETFs, bonds, sukuks, mutual funds)")

    # Add new position form
    with st.form("enbd_add_form", clear_on_submit=True):
        cols = st.columns(2)
        symbol = cols[0].text_input("Symbol / Ticker *", placeholder="e.g. AAPL, 2222.SR")
        description = cols[1].text_input("Description", placeholder="e.g. Saudi Aramco")

        cols2 = st.columns(3)
        asset_type = cols2[0].selectbox(
            "Asset Type *",
            options=[
                AssetType.STOCK.value,
                AssetType.ETF.value,
                AssetType.BOND.value,
                AssetType.SUKUK.value,
                AssetType.MUTUAL_FUND.value,
                AssetType.OTHER.value,
            ],
            format_func=lambda x: x.replace("_", " ").title(),
        )
        currency = cols2[1].selectbox("Currency *", options=["AED", "USD"], index=0)
        quantity = cols2[2].number_input("Quantity *", min_value=0.0, step=1.0, format="%.2f")

        cols3 = st.columns(3)
        mark_price = cols3[0].number_input("Current Price", min_value=0.0, step=0.01, format="%.4f")
        market_value = cols3[1].number_input(
            "Market Value",
            min_value=0.0,
            step=100.0,
            format="%.2f",
            help="Auto-calculated from Qty x Price if left at 0",
        )
        cost_basis = cols3[2].number_input("Cost Basis", min_value=0.0, step=100.0, format="%.2f")

        cols4 = st.columns(2)
        sector = cols4[0].text_input(
            "Sector (optional)",
            placeholder="e.g. Technology, Energy",
            help="Used in sector concentration alerts",
        )
        notes = cols4[1].text_input("Notes (optional)", placeholder="e.g. Held in brokerage account")

        submitted = st.form_submit_button("Add Position")
        if submitted:
            if not symbol or quantity <= 0:
                st.error("Symbol and Quantity are required.")
            else:
                # Auto-calculate market value if not provided
                mv = market_value if market_value > 0 else quantity * mark_price
                cb = cost_basis if cost_basis > 0 else mv
                mp = mark_price if mark_price > 0 else (mv / quantity if quantity else 0)

                pos = make_manual_position(
                    source="enbd",
                    symbol=symbol.upper().strip(),
                    description=description or symbol.upper().strip(),
                    asset_type=asset_type,
                    quantity=str(quantity),
                    market_value=str(mv),
                    cost_basis=str(cb),
                    currency=currency,
                    mark_price=str(mp),
                    notes=notes,
                    sector=sector.strip(),
                )
                add_manual_position(user_id, "enbd", pos)
                # Invalidate cached portfolio
                st.session_state.pop("data_key", None)
                st.success(f"Added {symbol.upper()}")
                st.rerun()

    # Show existing positions
    existing = _load_raw(user_id, "enbd")
    if existing:
        st.divider()
        st.subheader(f"Current Manual Asset Holdings ({len(existing)})")
        for mp in existing:
            col1, col2, col3, col4, col5 = st.columns([2, 1, 1, 2, 1])
            col1.write(f"**{mp.symbol}** ({mp.description})")
            col2.write(mp.asset_type.replace("_", " ").title())
            col3.write(f"{mp.currency} {float(mp.market_value):,.2f}")
            col4.write(f"Qty: {float(mp.quantity):,.2f} @ {float(mp.mark_price):,.4f}")
            if col5.button("Delete", key=f"del_enbd_{mp.id}"):
                delete_manual_position(user_id, "enbd", mp.id)
                st.session_state.pop("data_key", None)
                st.rerun()
    else:
        st.info("No manual asset positions added yet. Use the form above to add your holdings.")


# ---------- Manual RSU Additions ----------

with tab_equate:
    st.subheader("Employee Stock (RSU) Portfolio")
    st.caption("Enter your vested and unvested employee shares")

    with st.form("equateplus_add_form", clear_on_submit=True):
        cols = st.columns(2)
        eq_symbol = cols[0].text_input("Company Ticker *", placeholder="e.g. MSFT")
        eq_description = cols[1].text_input("Company Name", placeholder="e.g. Microsoft Corporation")

        cols2 = st.columns(3)
        vested_qty = cols2[0].number_input("Vested Shares *", min_value=0.0, step=1.0, format="%.2f")
        unvested_qty = cols2[1].number_input("Unvested Shares", min_value=0.0, step=1.0, format="%.2f")
        eq_price = cols2[2].number_input("Current Share Price *", min_value=0.0, step=0.01, format="%.2f")

        cols3 = st.columns(2)
        eq_currency = cols3[0].selectbox("Currency", options=["USD", "EUR", "GBP", "AED"], index=0, key="eq_currency")
        eq_sector = cols3[1].text_input(
            "Sector (optional)",
            placeholder="e.g. Technology, Energy",
            help="Used in sector concentration alerts",
        )

        eq_submitted = st.form_submit_button("Add Employee Stock")
        if eq_submitted:
            if not eq_symbol or vested_qty <= 0 or eq_price <= 0:
                st.error("Ticker, Vested Shares, and Current Price are required.")
            else:
                mv = vested_qty * eq_price
                pos = make_manual_position(
                    source="equateplus",
                    symbol=eq_symbol.upper().strip(),
                    description=eq_description or eq_symbol.upper().strip(),
                    asset_type=AssetType.RSU.value,
                    quantity=str(vested_qty),
                    market_value=str(mv),
                    cost_basis="0",  # RSUs typically have $0 cost basis
                    currency=eq_currency,
                    mark_price=str(eq_price),
                    unvested_quantity=str(unvested_qty),
                    sector=eq_sector.strip(),
                )
                add_manual_position(user_id, "equateplus", pos)
                st.session_state.pop("data_key", None)
                st.success(f"Added {eq_symbol.upper()}")
                st.rerun()

    # Show existing positions
    eq_existing = _load_raw(user_id, "equateplus")
    if eq_existing:
        st.divider()
        st.subheader(f"Current RSU Holdings ({len(eq_existing)})")
        for mp in eq_existing:
            col1, col2, col3, col4, col5 = st.columns([2, 2, 2, 2, 1])
            col1.write(f"**{mp.symbol}** ({mp.description})")
            col2.write(f"Vested: {float(mp.quantity):,.0f} shares")
            unvested = float(mp.unvested_quantity) if mp.unvested_quantity else 0
            col3.write(f"Unvested: {unvested:,.0f} shares")
            col4.write(f"{mp.currency} {float(mp.market_value):,.2f}")
            if col5.button("Delete", key=f"del_eq_{mp.id}"):
                delete_manual_position(user_id, "equateplus", mp.id)
                st.session_state.pop("data_key", None)
                st.rerun()

        # Summary
        total_vested = sum(float(mp.quantity) for mp in eq_existing)
        total_unvested = sum(float(mp.unvested_quantity or 0) for mp in eq_existing)
        total_value = sum(float(mp.market_value) for mp in eq_existing)
        st.divider()
        summary_cols = st.columns(3)
        summary_cols[0].metric("Total Vested", f"{total_vested:,.0f} shares")
        summary_cols[1].metric("Total Unvested", f"{total_unvested:,.0f} shares")
        summary_cols[2].metric("Vested Value", f"${total_value:,.2f}")
        st.caption("Only vested shares are included in portfolio analysis.")
    else:
        st.info("No RSU positions added yet. Use the form above to add your employee stock grants.")
