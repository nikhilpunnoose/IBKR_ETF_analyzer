# Architecture

## Data Flow

```
IBKR Flex Query (or saved XML file)
        │
        ▼
   fetcher/ibkr.py          Parse XML into Position objects
        │
        ▼
   fetcher/etf_holdings.py   Query yfinance to classify which positions are ETFs,
        │                    then fetch their holdings, sectors, expense ratios
        │
        ▼  (cached in SQLite via cache/store.py)
        │
        ▼
   models.Portfolio          All data assembled into one object
        │
        ├──► analysis/lookthrough.py     Decompose ETFs into underlying stocks
        ├──► analysis/overlap.py         Find shared holdings between ETF pairs
        ├──► analysis/fees.py            Compare expense ratios to cheaper alternatives
        └──► analysis/concentration.py   Flag over-concentration risks
                │
                ▼
        display/tables.py    Render everything as Rich terminal tables
```

## File-by-File Guide

### models.py

Defines all shared data structures as Python dataclasses. Every other module imports from here.

- **Position** — a single holding from IBKR: symbol, quantity, market value, cost basis, P&L, currency
- **ETFHolding** — one stock inside an ETF, with its percentage weight
- **ETFInfo** — everything we know about an ETF: name, expense ratio, category (e.g. "Large Blend"), fund family, top holdings, sector weights
- **EffectiveExposure** — your actual dollar exposure to a single underlying stock, combining direct holdings and look-through contributions from ETFs
- **OverlapPair** — two ETFs and how much they overlap (shared holdings, overlap coefficient)
- **FeeAlternative** — a suggestion to switch from one ETF to a cheaper one
- **ConcentrationAlert** — a warning that something exceeds a threshold (single stock, sector, or top-10)
- **Portfolio** — the top-level container: all positions, all ETF info, total value, report date

### config.py

Loads two sources of configuration:

1. `.env` file — your IBKR secrets (flex token and query ID)
2. `config.yaml` — tuneable settings: cache TTL, concentration warning thresholds, list of known cheap ETFs by category

Returns a typed `AppConfig` object. If IBKR credentials are missing, `ibkr` will be `None` (you can still use `--from-file`).

### fetcher/ibkr.py

Two ways to get positions:

- `fetch_positions(token, query_id)` — calls IBKR's Flex Web Service API via the `ibflex` library. Makes two HTTP requests: one to request the report, one to download it. Returns parsed positions.
- `load_from_file(path)` — reads a saved Flex Query XML file from disk. Same parsing, no network call.

Both convert IBKR's raw data into our `Position` dataclass. Important: IBKR labels both stocks and ETFs as `"STK"`, so at this stage we can't tell them apart. That happens next.

### fetcher/etf_holdings.py

Does two things:

1. **Identifies ETFs** — for each position classified as STOCK, queries yfinance to check its `quoteType`. If it's `"ETF"`, we reclassify it.
2. **Fetches ETF data** — for each identified ETF, pulls from yfinance:
   - Top ~10 holdings with weights (this is a yfinance limitation — it doesn't return the full list)
   - Sector weights (these cover the full ETF, not just top 10)
   - Expense ratio
   - Category and fund family

Multiple fallback paths for each field since yfinance's data structure varies across ETFs.

### cache/store.py

A SQLite-backed cache so we don't call yfinance on every run. ETF data changes slowly, so a 7-day TTL is the default.

- `get_etf_info(symbol)` — returns cached data if it exists and is less than TTL days old, otherwise `None`
- `put_etf_info(symbol, info)` — stores ETF data with today's date
- `clear()` — wipes the cache (used by `portfolio_analyzer cache --clear`)

The database is a single file at `~/.portfolio_analyzer/cache/etf_cache.db`.

### analysis/lookthrough.py

The core analysis. Answers the question: "What stocks do I actually own, across all my ETFs?"

Algorithm:
1. Start with direct stock positions (e.g. if you hold 30 shares of AAPL directly, that's $5,550)
2. For each ETF position, multiply the ETF's market value by each holding's weight to get an effective dollar amount (e.g. VTI is worth $28,050 and AAPL is 6.5% of VTI, so that's $1,823 of effective AAPL exposure through VTI)
3. Sum up all contributions per stock
4. Compute each stock's weight as a percentage of total portfolio value
5. Sort by total value descending

Output: a ranked list of `EffectiveExposure` objects showing your real stock-level exposure.

### analysis/overlap.py

Compares every pair of ETFs to find shared holdings.

For each pair it computes:
- Which stocks appear in both (by ticker symbol)
- The combined weight of overlapping stocks in each ETF
- An overlap coefficient: `number_of_shared / min(holdings_count_A, holdings_count_B)`. This is 1.0 when every holding in the smaller ETF also appears in the larger one (e.g. VTI vs VOO).

Only pairs with at least one shared holding are returned, sorted by overlap coefficient.

### analysis/fees.py

Compares each ETF's expense ratio against a configurable list of known cheap alternatives in the same category (defined in `config.yaml`).

For each ETF, if there's a cheaper alternative in the same category, it computes:
- `estimated_annual_savings = position_market_value × (current_ER - alternative_ER)`

Also has `compute_total_annual_fees()` which sums `market_value × expense_ratio` across all ETF positions to show total annual cost.

### analysis/concentration.py

Three concentration checks, each with a configurable threshold:

1. **Single stock** (default >5%) — any underlying stock that exceeds the threshold after look-through. Shows where the exposure comes from (direct + which ETFs).
2. **Sector** (default >30%) — aggregates sector weights across all ETFs, weighted by position size. Flags any sector over the threshold.
3. **Top 10** (default >40%) — if the top 10 underlying stocks make up more than the threshold of total portfolio value.

Also has `compute_sector_breakdown()` for the sector bar chart display.

### display/tables.py

Pure presentation layer. Takes analysis results and renders them as Rich tables:

- Portfolio summary (total value, position count, annual fees)
- Positions table (sorted by market value, P&L color-coded green/red)
- Effective exposures table (top N stocks with ETF source breakdown)
- Overlap table (ETF pairs with shared holdings)
- Fee alternatives table
- Concentration alerts (yellow/red panels)
- Sector breakdown (horizontal bar chart)

### cli.py

Orchestrates the full pipeline:

1. Parse CLI arguments
2. Load config
3. Get positions (live fetch or from file)
4. Identify ETFs and fetch their data
5. Build the Portfolio object
6. Run whichever analyses were requested
7. Display results

Supports subcommands (`fetch`, `report`, `cache`) and flags to run individual analyses (`--overlap`, `--fees`, `--exposure`, `--concentration`).

### __main__.py

One line: calls `cli.main()`. This is what makes `python -m portfolio_analyzer` work.
