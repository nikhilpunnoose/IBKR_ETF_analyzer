# Portfolio Analyzer

CLI tool that analyzes your Interactive Brokers portfolio. Looks through your ETFs to the underlying stocks and flags overlap, high fees, and concentration risks.

## Setup

### 1. Install Python dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

> **WSL users:** If you get permission errors creating a venv on an NTFS mount, create it in `/tmp` instead:
> ```bash
> python3 -m venv /tmp/pa_venv
> source /tmp/pa_venv/bin/activate
> pip install ibflex yfinance rich pandas pyyaml python-dotenv pytest
> ```

### 2. Configure IBKR Flex Query

You need to set up a Flex Query in IBKR that reports your open positions:

1. Log into [IBKR Client Portal](https://portal.interactivebrokers.com)
2. Go to **Performance & Reports > Flex Queries**
3. Under **Activity Flex Queries**, click **+** to create a new query
4. Give it a name (e.g. "Positions for Analyzer")
5. In the **Sections** area, check **Open Positions**
6. Select these fields: `Symbol`, `ISIN`, `Description`, `Asset Category`, `Position`, `Mark Price`, `Position Value`, `Cost Basis Money`, `Currency`, `FIFO Pnl Unrealized`
7. Set **Period** to "Last Business Day"
8. Set **Format** to XML
9. Save the query and note the **Query ID** shown next to it

Then generate an API token:

1. Go to **Performance & Reports > Flex Queries > Flex Web Service Configuration**
2. Click **Generate New Token**
3. Choose an expiry (up to 1 year)
4. Copy the token

### 3. Create your .env file

```bash
cp .env.example .env
```

Edit `.env` and fill in your values:

```
IBKR_FLEX_TOKEN=your_token_here
IBKR_QUERY_ID=your_query_id_here
```

## Usage

### Full report (live IBKR fetch)

```bash
python -m portfolio_analyzer
```

This fetches your current positions from IBKR, identifies which ones are ETFs, pulls their holdings data from Yahoo Finance, and runs all analyses.

### Using a saved XML file

If you don't have credentials set up yet, or want to test offline:

```bash
python -m portfolio_analyzer --from-file tests/fixtures/sample_flex_response.xml
```

### Individual analyses

```bash
python -m portfolio_analyzer report --exposure        # Look-through stock exposures
python -m portfolio_analyzer report --overlap          # ETF overlap detection
python -m portfolio_analyzer report --fees             # Fee optimization suggestions
python -m portfolio_analyzer report --concentration    # Concentration risk alerts
python -m portfolio_analyzer report --top 30           # Show top 30 exposures (default 20)
```

### Other commands

```bash
python -m portfolio_analyzer fetch          # Just fetch and display positions
python -m portfolio_analyzer cache --clear  # Clear cached ETF data
python -m portfolio_analyzer -v             # Verbose logging
```

## What it reports

**Portfolio Summary** — total value, number of positions, annual ETF fees.

**Positions Table** — all holdings sorted by market value, with unrealized P&L.

**Effective Exposures** — your actual stock-level exposure after looking through all ETFs. For example, if you hold VTI and VOO, both contain Apple — this shows your combined Apple exposure.

**ETF Overlap** — which ETFs share the same underlying stocks, and how much they overlap. A coefficient of 1.0 means complete overlap (e.g. VTI and VOO overlap heavily since the S&P 500 is a subset of the total US market).

**Fee Optimization** — if you hold an ETF and there's a cheaper alternative in the same category, it shows the alternative and estimated annual savings.

**Concentration Alerts** — warnings when:
- Any single stock exceeds 5% of your portfolio (after look-through)
- Any sector exceeds 30%
- Your top 10 stocks exceed 40%

**Sector Breakdown** — a bar chart showing your portfolio's sector allocation.

## Configuration

Edit `config.yaml` to adjust:

- **Cache TTL** — how many days before ETF data is re-fetched (default: 7)
- **Concentration thresholds** — when to trigger alerts
- **Fee alternatives** — the list of known cheap ETFs by category that fee analysis compares against

## Limitations

- **ETF holdings are top ~10 only.** Yahoo Finance returns roughly the top 10 holdings per ETF, not the full list. This is enough for overlap and concentration detection (the top holdings dominate the weight), but it means the look-through won't capture every small holding. Sector weights cover the full ETF.
- **IBKR labels ETFs as stocks.** The tool uses Yahoo Finance to distinguish ETFs from individual stocks, which requires a network call per unique symbol on first run (cached afterward).
- **Fee alternatives are manually maintained.** The list in `config.yaml` covers common US categories. Add your own if you hold niche ETFs.

## Running tests

```bash
python -m pytest tests/ -v
```

Tests use fixture data and don't make any network calls.
