from __future__ import annotations

from decimal import Decimal

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from portfolio_analyzer.models import (
    ConcentrationAlert,
    EffectiveExposure,
    FeeAlternative,
    OverlapPair,
    Portfolio,
    Position,
)

console = Console()


def show_portfolio_summary(portfolio: Portfolio, total_fees: Decimal) -> None:
    table = Table(title="Portfolio Summary", show_header=False, title_style="bold cyan")
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")
    table.add_row("Report Date", str(portfolio.report_date or "N/A"))
    table.add_row("Total Value", f"${portfolio.total_value:,.2f}")
    table.add_row("Positions", str(len(portfolio.positions)))
    etf_count = sum(1 for p in portfolio.positions if p.symbol in portfolio.etf_info)
    table.add_row("ETFs", str(etf_count))
    table.add_row("Annual ETF Fees", f"${total_fees:,.2f}")
    console.print()
    console.print(table)


def show_positions(positions: list[Position]) -> None:
    table = Table(title="Current Positions", title_style="bold cyan")
    table.add_column("Symbol", style="cyan")
    table.add_column("Type")
    table.add_column("Qty", justify="right")
    table.add_column("Mkt Value", justify="right", style="green")
    table.add_column("Cost Basis", justify="right")
    table.add_column("Unrealized P&L", justify="right")
    table.add_column("Ccy")

    for p in sorted(positions, key=lambda x: x.market_value, reverse=True):
        pnl_style = "green" if p.unrealized_pnl >= 0 else "red"
        table.add_row(
            p.symbol,
            p.asset_type.value,
            f"{p.quantity:,.0f}",
            f"${p.market_value:,.2f}",
            f"${p.cost_basis:,.2f}",
            Text(f"${p.unrealized_pnl:,.2f}", style=pnl_style),
            p.currency,
        )
    console.print()
    console.print(table)


def show_effective_exposures(exposures: list[EffectiveExposure], top_n: int = 20) -> None:
    table = Table(title=f"Top {top_n} Effective Stock Exposures (Look-Through)", title_style="bold cyan")
    table.add_column("#", justify="right", style="dim")
    table.add_column("Stock", style="cyan")
    table.add_column("Total Value", justify="right", style="green")
    table.add_column("% Portfolio", justify="right")
    table.add_column("Direct", justify="right")
    table.add_column("Via ETFs", justify="right")
    table.add_column("ETF Sources")

    for i, exp in enumerate(exposures[:top_n], 1):
        etf_total = sum(exp.etf_contributions.values(), Decimal(0))
        etf_sources = ", ".join(f"{etf}(${v:,.0f})" for etf, v in exp.etf_contributions.items())
        table.add_row(
            str(i),
            exp.symbol,
            f"${exp.total_value:,.2f}",
            f"{exp.weight_of_portfolio:.2%}",
            f"${exp.direct_value:,.2f}" if exp.direct_value else "-",
            f"${etf_total:,.2f}" if etf_total else "-",
            etf_sources or "-",
        )
    console.print()
    console.print(table)


def show_overlap(pairs: list[OverlapPair]) -> None:
    if not pairs:
        console.print("\n[dim]No ETF overlap detected.[/dim]")
        return
    table = Table(title="ETF Holding Overlap", title_style="bold cyan")
    table.add_column("ETF A", style="cyan")
    table.add_column("ETF B", style="cyan")
    table.add_column("Shared", justify="right")
    table.add_column("Overlap Coeff", justify="right")
    table.add_column("Overlap in A", justify="right")
    table.add_column("Overlap in B", justify="right")
    table.add_column("Shared Stocks")

    for p in pairs:
        preview = ", ".join(p.shared_holdings[:5])
        if len(p.shared_holdings) > 5:
            preview += "..."
        table.add_row(
            p.etf_a,
            p.etf_b,
            str(len(p.shared_holdings)),
            f"{p.overlap_coefficient:.2f}",
            f"{p.overlap_weight_a:.1%}",
            f"{p.overlap_weight_b:.1%}",
            preview,
        )
    console.print()
    console.print(table)


def show_fee_alternatives(alternatives: list[FeeAlternative]) -> None:
    if not alternatives:
        console.print("\n[dim]No cheaper ETF alternatives found.[/dim]")
        return
    table = Table(title="Fee Optimization Opportunities", title_style="bold cyan")
    table.add_column("Current ETF", style="cyan")
    table.add_column("ER", justify="right")
    table.add_column("Alternative", style="green")
    table.add_column("Alt ER", justify="right")
    table.add_column("Est. Annual Savings", justify="right", style="green bold")
    table.add_column("Category")

    for a in alternatives:
        table.add_row(
            a.current_etf,
            f"{a.current_expense_ratio:.4f}",
            a.alternative_etf,
            f"{a.alternative_expense_ratio:.4f}",
            f"${a.estimated_annual_savings:,.2f}",
            a.alternative_category,
        )
    console.print()
    console.print(table)


def show_concentration_alerts(alerts: list[ConcentrationAlert]) -> None:
    if not alerts:
        console.print("\n[green]No concentration alerts.[/green]")
        return
    console.print()
    for alert in alerts:
        style = "yellow" if alert.weight < alert.threshold * 1.5 else "red bold"
        console.print(
            Panel(
                Text(alert.message, style=style),
                title=f"[{alert.alert_type.upper()}] {alert.entity}",
                border_style=style,
            )
        )


def show_sector_breakdown(sector_pcts: dict[str, float], total_value: float) -> None:
    if not sector_pcts:
        return
    table = Table(title="Sector Breakdown", title_style="bold cyan")
    table.add_column("Sector")
    table.add_column("Value", justify="right")
    table.add_column("Weight", justify="right")
    table.add_column("", min_width=30)

    for sector, value in sector_pcts.items():
        pct = value / total_value if total_value else 0.0
        bar_len = int(pct * 50)
        bar = "=" * bar_len
        table.add_row(sector, f"${value:,.0f}", f"{pct:.1%}", f"[cyan]{bar}[/cyan]")
    console.print()
    console.print(table)
