from datetime import date
from decimal import Decimal

import pytest

from portfolio_analyzer.models import (
    AssetType,
    ETFHolding,
    ETFInfo,
    Portfolio,
    Position,
)


def _make_position(symbol, asset_type, market_value, cost_basis=None, description=""):
    return Position(
        symbol=symbol,
        isin=None,
        description=description or symbol,
        asset_type=asset_type,
        quantity=Decimal(1),
        market_value=Decimal(str(market_value)),
        cost_basis=Decimal(str(cost_basis or market_value)),
        currency="USD",
        mark_price=Decimal(str(market_value)),
        unrealized_pnl=Decimal(str(market_value - (cost_basis or market_value))),
        report_date=date(2026, 2, 7),
    )


@pytest.fixture
def sample_etf_info():
    return {
        "VTI": ETFInfo(
            symbol="VTI",
            name="Vanguard Total Stock Market ETF",
            expense_ratio=0.0003,
            category="Large Blend",
            family="Vanguard",
            top_holdings=[
                ETFHolding("AAPL", "Apple Inc", 0.065),
                ETFHolding("MSFT", "Microsoft Corp", 0.060),
                ETFHolding("NVDA", "NVIDIA Corp", 0.050),
                ETFHolding("AMZN", "Amazon.com Inc", 0.035),
                ETFHolding("GOOGL", "Alphabet Inc", 0.020),
            ],
            sector_weights={"Technology": 0.30, "Healthcare": 0.13, "Financial Services": 0.13, "Consumer Cyclical": 0.10},
            asset_classes={"stock": 0.99, "cash": 0.01},
            total_net_assets=None,
            fetched_at=date(2026, 2, 7),
        ),
        "VOO": ETFInfo(
            symbol="VOO",
            name="Vanguard S&P 500 ETF",
            expense_ratio=0.0003,
            category="Large Blend",
            family="Vanguard",
            top_holdings=[
                ETFHolding("AAPL", "Apple Inc", 0.070),
                ETFHolding("MSFT", "Microsoft Corp", 0.065),
                ETFHolding("NVDA", "NVIDIA Corp", 0.055),
                ETFHolding("AMZN", "Amazon.com Inc", 0.038),
                ETFHolding("GOOGL", "Alphabet Inc", 0.022),
            ],
            sector_weights={"Technology": 0.32, "Healthcare": 0.12, "Financial Services": 0.14, "Consumer Cyclical": 0.11},
            asset_classes={"stock": 0.99, "cash": 0.01},
            total_net_assets=None,
            fetched_at=date(2026, 2, 7),
        ),
        "VXUS": ETFInfo(
            symbol="VXUS",
            name="Vanguard Total International Stock ETF",
            expense_ratio=0.0005,
            category="Foreign Large Blend",
            family="Vanguard",
            top_holdings=[
                ETFHolding("TSM", "Taiwan Semiconductor", 0.020),
                ETFHolding("NOVO-B.CO", "Novo Nordisk", 0.015),
                ETFHolding("ASML", "ASML Holding", 0.012),
                ETFHolding("SAP", "SAP SE", 0.010),
            ],
            sector_weights={"Technology": 0.15, "Financial Services": 0.20, "Healthcare": 0.10, "Industrials": 0.12},
            asset_classes={"stock": 0.98, "cash": 0.02},
            total_net_assets=None,
            fetched_at=date(2026, 2, 7),
        ),
    }


@pytest.fixture
def sample_portfolio(sample_etf_info):
    positions = [
        _make_position("VTI", AssetType.ETF, 28050, 25000, "VANGUARD TOTAL STOCK MKT ETF"),
        _make_position("VOO", AssetType.ETF, 25500, 22000, "VANGUARD S&P 500 ETF"),
        _make_position("VXUS", AssetType.ETF, 12050, 11000, "VANGUARD TOTAL INTL STOCK ETF"),
        _make_position("AAPL", AssetType.STOCK, 5550, 4500, "APPLE INC"),
    ]
    total_value = sum(p.market_value for p in positions)
    return Portfolio(
        positions=positions,
        etf_info=sample_etf_info,
        total_value=total_value,
        report_date=date(2026, 2, 7),
    )
