from __future__ import annotations

import argparse
import logging
import sys

from rich.console import Console

from portfolio_analyzer.analysis import concentration, fees, lookthrough, overlap
from portfolio_analyzer.analysis import asset_class
from portfolio_analyzer.cache.store import CacheStore
from portfolio_analyzer.config import load_config
from portfolio_analyzer.display import tables
from portfolio_analyzer.fetcher.consolidate import build_consolidated_portfolio
from portfolio_analyzer.fetcher.etf_holdings import fetch_all_etf_info, identify_etfs
from portfolio_analyzer.fetcher.ibkr import fetch_positions, load_from_file
from portfolio_analyzer.fetcher.manual import load_manual_positions
from portfolio_analyzer.models import AssetType, Portfolio

console = Console()
logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="portfolio_analyzer",
        description="Analyze your portfolio: ETF look-through, overlap, fees, concentration, asset classes",
    )
    parser.add_argument("--from-file", type=str, default=None, help="Load IBKR positions from a Flex XML file")
    parser.add_argument("--etoro-file", type=str, default=None, help="Load positions from an eToro XLS/XLSX export")
    parser.add_argument("--include-manual", action="store_true", help="Include manually entered positions (ENBD, EquatePlus)")
    parser.add_argument("--config", type=str, default="config.yaml", help="Path to config.yaml")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")

    sub = parser.add_subparsers(dest="command")

    sub.add_parser("fetch", help="Fetch and display positions only")

    report_p = sub.add_parser("report", help="Run analysis report")
    report_p.add_argument("--overlap", action="store_true", help="Show overlap analysis only")
    report_p.add_argument("--fees", action="store_true", help="Show fee analysis only")
    report_p.add_argument("--exposure", action="store_true", help="Show look-through exposure only")
    report_p.add_argument("--concentration", action="store_true", help="Show concentration only")
    report_p.add_argument("--asset-class", action="store_true", help="Show asset class breakdown")
    report_p.add_argument("--top", type=int, default=20, help="Number of top exposures to show")

    cache_p = sub.add_parser("cache", help="Cache management")
    cache_p.add_argument("--clear", action="store_true", help="Clear ETF holdings cache")

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s: %(message)s",
    )

    config = load_config(args.config)
    cache = CacheStore(config.cache.directory / "etf_cache.db", config.cache.etf_holdings_ttl_days)

    try:
        if args.command == "cache":
            if args.clear:
                cache.clear()
                console.print("[green]Cache cleared.[/green]")
            return

        # Step 1: Get positions from all sources
        positions = _load_all_positions(args, config)
        if not positions:
            console.print("[red]No positions found.[/red]")
            return

        sources = set(p.source for p in positions)
        if len(sources) > 1:
            console.print(f"Sources: {', '.join(s.upper() for s in sorted(sources))}")

        if args.command == "fetch":
            tables.show_positions(positions)
            return

        # Step 2: Identify ETFs (tries exchange suffixes for European-listed ETFs)
        with console.status("Identifying ETFs (trying exchange suffixes)..."):
            stock_symbols = list({p.symbol for p in positions if p.asset_type in (AssetType.STOCK, AssetType.OTHER)})
            etf_map = identify_etfs(stock_symbols)

        for pos in positions:
            if pos.symbol in etf_map:
                pos.asset_type = AssetType.ETF

        etf_display = [f"{k} -> {v}" if k != v else k for k, v in etf_map.items()]
        console.print(f"Found {len(etf_map)} ETFs: {', '.join(etf_display)}")

        # Step 3: Fetch ETF holdings
        with console.status("Fetching ETF holdings data..."):
            etf_info = fetch_all_etf_info(etf_map, cache)

        # Step 3b: Apply expense ratio overrides from config
        for sym, er in config.expense_ratio_overrides.items():
            if sym in etf_info:
                etf_info[sym].expense_ratio = er

        # Step 4: Build consolidated portfolio
        sources_dict = {}
        for p in positions:
            sources_dict.setdefault(p.source, []).append(p)
        portfolio = build_consolidated_portfolio(
            sources=sources_dict,
            etf_info=etf_info,
            currency_rates=config.currency.rates,
            base_currency=config.currency.base,
            report_date=positions[0].report_date if positions else None,
        )

        # Step 5: Run analyses and display
        _run_report(args, portfolio, config)

    finally:
        cache.close()


def _load_all_positions(args: argparse.Namespace, config) -> list:
    positions = []

    # IBKR source
    if args.from_file:
        console.print(f"Loading IBKR positions from [cyan]{args.from_file}[/cyan]")
        positions.extend(load_from_file(args.from_file))
    elif config.ibkr:
        with console.status("Fetching positions from IBKR..."):
            positions.extend(fetch_positions(config.ibkr.flex_token, config.ibkr.query_id))

    # eToro source
    if args.etoro_file:
        console.print(f"Loading eToro positions from [cyan]{args.etoro_file}[/cyan]")
        from portfolio_analyzer.fetcher.etoro import parse_etoro_file
        positions.extend(parse_etoro_file(args.etoro_file))

    # Manual positions (ENBD + EquatePlus)
    if args.include_manual:
        for source in ("enbd", "equateplus"):
            manual = load_manual_positions(user_id=None, source=source)
            if manual:
                console.print(f"Loaded {len(manual)} manual positions from [cyan]{source.upper()}[/cyan]")
                positions.extend(manual)

    if not positions and not args.from_file and config.ibkr is None:
        console.print("[red]No data sources configured.[/red]")
        console.print("[dim]Use --from-file, --etoro-file, or --include-manual.[/dim]")
        sys.exit(1)

    return positions


def _run_report(args: argparse.Namespace, portfolio: Portfolio, config) -> None:
    total_annual_fees = fees.compute_total_annual_fees(portfolio)
    tables.show_portfolio_summary(portfolio, total_annual_fees)
    tables.show_positions(portfolio.positions)

    effective = lookthrough.compute_effective_exposures(
        portfolio,
        currency_rates=config.currency.rates,
        base_currency=config.currency.base,
    )

    report_args = args if args.command == "report" else argparse.Namespace(
        overlap=False, fees=False, exposure=False, concentration=False,
        asset_class=False, top=20,
    )
    show_all = not any([
        report_args.overlap, report_args.fees, report_args.exposure,
        report_args.concentration, report_args.asset_class,
    ])
    top_n = report_args.top

    if show_all or report_args.exposure:
        tables.show_effective_exposures(effective, top_n=top_n)

    if show_all or report_args.overlap:
        overlap_pairs = overlap.compute_overlap(portfolio)
        tables.show_overlap(overlap_pairs)

    if show_all or report_args.fees:
        fee_alts = fees.analyze_fees(portfolio, config.analysis.fee_alternatives)
        tables.show_fee_alternatives(fee_alts)

    if show_all or report_args.concentration:
        alerts = concentration.analyze_concentration(
            portfolio,
            effective,
            single_stock_warn=config.analysis.single_stock_warn,
            sector_warn=config.analysis.sector_warn,
            top10_warn=config.analysis.top10_warn,
            currency_rates=config.currency.rates,
            base_currency=config.currency.base,
        )
        tables.show_concentration_alerts(alerts)
        sector_pcts = concentration.compute_sector_breakdown(
            portfolio,
            currency_rates=config.currency.rates,
            base_currency=config.currency.base,
        )
        tables.show_sector_breakdown(sector_pcts, float(portfolio.total_value))

    if show_all or report_args.asset_class:
        breakdown = asset_class.compute_asset_class_breakdown(
            portfolio,
            overrides=config.asset_class_overrides,
            currency_rates=config.currency.rates,
            base_currency=config.currency.base,
        )
        tables.show_asset_class_breakdown(breakdown)
