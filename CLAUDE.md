# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Environment Setup

This project runs on WSL2 with the repo on an NTFS mount. Editable pip installs and `.venv` creation fail on NTFS, so the venv lives on the Linux filesystem at `~/.local/share/pa_venv`:

```bash
bash setup.sh                # creates ~/.local/share/pa_venv (one-time)
. ~/.local/share/pa_venv/bin/activate
```

## Common Commands

```bash
# Activate venv (required before all commands)
. ~/.local/share/pa_venv/bin/activate

# Run the CLI (PYTHONPATH needed since editable install doesn't work)
PYTHONPATH=. python3 -m portfolio_analyzer --from-file tests/fixtures/sample_flex_response.xml

# Run all tests
PYTHONPATH=. python3 -m pytest tests/ -v

# Run a single test file
PYTHONPATH=. python3 -m pytest tests/test_lookthrough.py -v

# Run a single test
PYTHONPATH=. python3 -m pytest tests/test_lookthrough.py::test_direct_holding_appears -v
```

## Architecture

The pipeline flows linearly: **fetch positions -> identify ETFs -> fetch ETF data -> analyze -> display**.

`cli.py` orchestrates this pipeline. `models.py` defines all shared dataclasses (Position, ETFInfo, Portfolio, etc.) that every module imports from.

**Data flow:**
1. `fetcher/ibkr.py` — parses IBKR Flex Query XML into `Position` objects. IBKR labels ETFs as `"STK"`, so ETF identification happens later.
2. `fetcher/etf_holdings.py` — queries yfinance to classify positions as ETFs (by `quoteType`), then fetches top holdings, sector weights, and expense ratios. Has multiple fallback paths since yfinance's data structure varies across ETFs.
3. `cache/store.py` — SQLite cache at `~/.portfolio_analyzer/cache/etf_cache.db` with configurable TTL (default 7 days) so yfinance isn't called every run.
4. `analysis/` — four independent modules (lookthrough, overlap, fees, concentration) that all take a `Portfolio` object and return result dataclasses.
5. `display/tables.py` — pure presentation layer using Rich tables. No business logic.

**Key design decisions:**
- ETF holdings data from yfinance is limited to top ~10 holdings (not the full list). Sector weights cover the full ETF. This is a known limitation.
- `config.yaml` has `expense_ratio_overrides` to fix bad yfinance data, and `fee_alternatives` listing known cheap ETFs by category (manually maintained).
- All monetary values use `Decimal`; weights/ratios use `float`.

## Testing

Tests use fixtures defined in `tests/conftest.py` (`sample_portfolio`, `sample_etf_info`). No network calls — all ETF data is hardcoded in fixtures. The `_make_position` helper in conftest creates Position objects with sensible defaults.

Test fixture file: `tests/fixtures/sample_flex_response.xml` (IBKR Flex Query XML).
