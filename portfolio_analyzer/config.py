from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv


@dataclass
class IBKRConfig:
    flex_token: str
    query_id: str


@dataclass
class CacheConfig:
    directory: Path
    etf_holdings_ttl_days: int


@dataclass
class AnalysisConfig:
    single_stock_warn: float
    sector_warn: float
    top10_warn: float
    fee_alternatives: dict[str, list[dict]] = field(default_factory=dict)


@dataclass
class CurrencyConfig:
    base: str = "USD"
    rates: dict[str, float] = field(default_factory=dict)


@dataclass
class AppConfig:
    ibkr: IBKRConfig | None
    cache: CacheConfig
    analysis: AnalysisConfig
    expense_ratio_overrides: dict[str, float] = field(default_factory=dict)
    currency: CurrencyConfig = field(default_factory=CurrencyConfig)
    asset_class_overrides: dict[str, str] = field(default_factory=dict)


def load_config(config_path: str = "config.yaml", env_path: str = ".env") -> AppConfig:
    load_dotenv(env_path)

    cfg: dict = {}
    config_file = Path(config_path)
    if config_file.exists():
        with open(config_file) as f:
            cfg = yaml.safe_load(f) or {}

    cache_cfg = cfg.get("cache", {})
    analysis_cfg = cfg.get("analysis", {})
    thresholds = analysis_cfg.get("concentration_thresholds", {})

    flex_token = os.environ.get("IBKR_FLEX_TOKEN", "")
    query_id = os.environ.get("IBKR_QUERY_ID", "")
    ibkr = IBKRConfig(flex_token=flex_token, query_id=query_id) if flex_token and query_id else None

    er_overrides_raw = cfg.get("expense_ratio_overrides", {}) or {}
    er_overrides = {k: float(v) for k, v in er_overrides_raw.items()}

    currency_cfg = cfg.get("currency", {})
    currency = CurrencyConfig(
        base=currency_cfg.get("base", "USD"),
        rates={k: float(v) for k, v in currency_cfg.get("rates", {}).items()},
    )

    ac_overrides_raw = cfg.get("asset_class_overrides", {}) or {}
    ac_overrides = {k: str(v) for k, v in ac_overrides_raw.items()}

    return AppConfig(
        ibkr=ibkr,
        cache=CacheConfig(
            directory=Path(cache_cfg.get("directory", "~/.portfolio_analyzer/cache")).expanduser(),
            etf_holdings_ttl_days=int(cache_cfg.get("etf_holdings_ttl_days", 7)),
        ),
        analysis=AnalysisConfig(
            single_stock_warn=float(thresholds.get("single_stock_warn", 0.05)),
            sector_warn=float(thresholds.get("sector_warn", 0.30)),
            top10_warn=float(thresholds.get("top10_warn", 0.40)),
            fee_alternatives=analysis_cfg.get("fee_alternatives", {}),
        ),
        expense_ratio_overrides=er_overrides,
        currency=currency,
        asset_class_overrides=ac_overrides,
    )
