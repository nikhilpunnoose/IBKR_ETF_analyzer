from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum


class AssetType(Enum):
    STOCK = "stock"
    ETF = "etf"
    BOND = "bond"
    OPTION = "option"
    CASH = "cash"
    MUTUAL_FUND = "mutual_fund"
    SUKUK = "sukuk"
    RSU = "rsu"
    CRYPTO = "crypto"
    OTHER = "other"


class AssetClassBucket(Enum):
    EQUITIES = "equities"
    FIXED_INCOME = "fixed_income"
    OTHER = "other"


@dataclass
class Position:
    """A single position in the portfolio."""

    symbol: str
    isin: str | None
    description: str
    asset_type: AssetType
    quantity: Decimal
    market_value: Decimal
    cost_basis: Decimal
    currency: str
    mark_price: Decimal
    unrealized_pnl: Decimal
    report_date: date
    source: str = "ibkr"
    sector: str = ""  # optional manual sector tag for concentration analysis


@dataclass
class ETFHolding:
    """A single stock within an ETF."""

    symbol: str
    name: str
    weight: float  # 0.0 to 1.0


@dataclass
class ETFInfo:
    """Metadata and holdings for one ETF."""

    symbol: str
    name: str
    expense_ratio: float | None
    category: str | None
    family: str | None
    top_holdings: list[ETFHolding]
    sector_weights: dict[str, float]
    asset_classes: dict[str, float]
    total_net_assets: float | None
    fetched_at: date


@dataclass
class EffectiveExposure:
    """The user's actual dollar exposure to a single underlying stock."""

    symbol: str
    name: str
    total_value: Decimal
    direct_value: Decimal
    etf_contributions: dict[str, Decimal] = field(default_factory=dict)
    weight_of_portfolio: float = 0.0


@dataclass
class OverlapPair:
    """Two ETFs and their overlap metrics."""

    etf_a: str
    etf_b: str
    shared_holdings: list[str]
    overlap_weight_a: float
    overlap_weight_b: float
    overlap_coefficient: float


@dataclass
class FeeAlternative:
    """A cheaper ETF suggestion."""

    current_etf: str
    current_expense_ratio: float
    alternative_etf: str
    alternative_expense_ratio: float
    alternative_category: str
    estimated_annual_savings: Decimal


@dataclass
class ConcentrationAlert:
    """A warning about portfolio concentration."""

    alert_type: str  # "sector", "top10", "single_stock"
    entity: str
    weight: float
    threshold: float
    message: str


@dataclass
class Portfolio:
    """The full portfolio state used by analysis modules."""

    positions: list[Position]
    etf_info: dict[str, ETFInfo]
    total_value: Decimal
    report_date: date | None


@dataclass
class AssetClassDetail:
    """How a single position contributes to asset class buckets."""

    symbol: str
    source: str
    asset_type: str
    market_value: Decimal
    equities_portion: Decimal
    fixed_income_portion: Decimal
    other_portion: Decimal


@dataclass
class AssetClassBreakdown:
    """Breakdown of portfolio into equities vs fixed income."""

    equities_value: Decimal
    equities_weight: float
    fixed_income_value: Decimal
    fixed_income_weight: float
    other_value: Decimal
    other_weight: float
    details: list[AssetClassDetail] = field(default_factory=list)


@dataclass
class ManualPosition:
    """A manually entered position for ENBD or EquatePlus."""

    id: str
    source: str  # "enbd" or "equateplus"
    symbol: str
    description: str
    asset_type: str  # AssetType value
    quantity: str  # stored as string, converted to Decimal
    market_value: str
    cost_basis: str
    currency: str
    mark_price: str
    notes: str = ""
    unvested_quantity: str = "0"
    updated_at: str = ""
    sector: str = ""  # optional sector tag surfaced in concentration analysis
