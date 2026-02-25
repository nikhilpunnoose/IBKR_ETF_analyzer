"""IBKR Flex Query setup guide page."""

import streamlit as st

st.title("How to Create an IBKR Flex Query")
st.caption("Step-by-step guide to exporting your portfolio data from Interactive Brokers")

# --- Overview ---
st.header("Overview")
st.markdown("""
This app analyzes your portfolio using an **IBKR Flex Query XML export**. A Flex Query is a
customizable report you configure once in your IBKR account, then download anytime to get a
snapshot of your current positions.

The whole setup takes about 5 minutes. You only need to do it once — after that, you can
re-download the XML whenever you want an updated analysis.
""")

# --- Step 1 ---
st.header("Step 1: Open the Flex Queries Page")
st.markdown("""
1. Log in to [IBKR Client Portal](https://portal.interactivebrokers.com/) or
   [Account Management](https://www.interactivebrokers.com/sso/Login)
2. Navigate to **Performance & Reports** (top menu)
3. Click **Flex Queries** in the left sidebar
4. Under **Custom Flex Queries**, click the **+** (Create) button to make a new query
""")

# --- Step 2 ---
st.header("Step 2: Configure the Query")
st.markdown("""
Give your query a name (e.g. "Portfolio Snapshot") and configure these settings:
""")

st.subheader("General Settings")
st.markdown("""
| Setting | Value |
|---|---|
| **Query Name** | Portfolio Snapshot (or any name you like) |
| **Date Period** | Last 7 Calendar Days (or any recent period) |
| **Format** | XML |
""")

st.subheader("Sections to Include")
st.markdown("""
You only need **one section**: **Open Positions**. Click on it to add it to your query.

You do **not** need: Trades, Cash Transactions, Dividends, etc. Adding extra sections won't
break anything, but they're ignored by the analyzer.
""")

# --- Step 3 ---
st.header("Step 3: Select Open Positions Fields")
st.markdown("""
After adding the **Open Positions** section, click on it to configure which fields to include.
Select at minimum these fields:
""")

col1, col2 = st.columns(2)
with col1:
    st.markdown("""
    **Required fields:**
    - Symbol
    - ISIN
    - Description
    - Asset Category
    - Position (quantity)
    - Position Value (market value)
    - Cost Basis Money
    - Currency
    - Mark Price
    - Report Date
    """)
with col2:
    st.markdown("""
    **Also include one of:**
    - FIFO Pnl Unrealized *(preferred)*
    - Unrealized P&L

    **Tip:** If you're unsure, just click
    **Select All** — extra fields are safely
    ignored by the analyzer.
    """)

st.info(
    "IBKR classifies ETFs as \"STK\" (stock) in the Asset Category field. "
    "This is normal — the analyzer automatically identifies which positions "
    "are actually ETFs using market data.",
    icon="\U00002139\U0000FE0F",
)

# --- Step 4 ---
st.header("Step 4: Save and Run the Query")
st.markdown("""
1. Click **Save** (or **Continue** / **Create**) to save your Flex Query
2. Back on the Flex Queries list, find your new query
3. Click the **Run** (arrow) button next to it
4. IBKR will generate the report — this may take a few seconds
5. Click **Download** to save the XML file to your computer
""")

# --- Step 5 ---
st.header("Step 5: Upload to Portfolio Analyzer")
st.markdown("""
1. Go to the **Portfolio Analyzer** page (use the sidebar navigation)
2. Select **Upload Flex Query XML**
3. Upload the `.xml` file you just downloaded
4. The analysis runs automatically
""")

# --- What the XML looks like ---
st.header("Reference: What the XML Looks Like")
st.markdown("Your downloaded file will have a structure like this:")
st.code("""<?xml version="1.0" encoding="UTF-8"?>
<FlexQueryResponse queryName="Portfolio Snapshot" type="AF">
  <FlexStatements count="1">
    <FlexStatement accountId="U1234567" toDate="2026-02-07">
      <OpenPositions>
        <OpenPosition
          symbol="VTI"
          description="VANGUARD TOTAL STOCK MKT ETF"
          assetCategory="STK"
          isin="US9229087690"
          position="100"
          markPrice="280.50"
          positionValue="28050.00"
          costBasisMoney="25000.00"
          currency="USD"
          fifoPnlUnrealized="3050.00"
          reportDate="2026-02-07"
        />
        <!-- more positions... -->
      </OpenPositions>
    </FlexStatement>
  </FlexStatements>
</FlexQueryResponse>""", language="xml")

# --- Privacy ---
st.header("Privacy & Security")
st.markdown("""
- Your XML file is processed **entirely in memory** — nothing is saved to disk or any database
- The file contains **positions only** — no account credentials, passwords, or trading permissions
- Your session data is discarded when you close the browser tab
- The only external calls made are to **Yahoo Finance** to fetch public ETF data (holdings,
  expense ratios, sectors)
- If you sign in and save your IBKR Flex Query credentials, the token is **encrypted** (Fernet)
  before storage and can be **deleted anytime** from Account Settings
""")

# --- Troubleshooting ---
st.header("Troubleshooting")

with st.expander("\"No positions found\" after upload"):
    st.markdown("""
    - Make sure you included the **Open Positions** section in your Flex Query
    - Check that the date period covers a time when you had open positions
    - Verify the file is XML format (not CSV or HTML)
    """)

with st.expander("Some ETFs not detected"):
    st.markdown("""
    - The analyzer uses Yahoo Finance to identify ETFs. Some region-specific ETFs
      (e.g. European-listed with tickers like VWCE) are resolved by trying common
      exchange suffixes (.L, .AS, .DE, etc.)
    - If an ETF isn't detected, it will appear as a stock position in the results
    """)

with st.expander("Expense ratios look wrong"):
    st.markdown("""
    - Yahoo Finance data isn't always accurate for expense ratios
    - The app has built-in overrides for known problem tickers
    - This only affects the fee analysis section — other analyses are unaffected
    """)
