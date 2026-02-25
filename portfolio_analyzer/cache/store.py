from __future__ import annotations

import json
import sqlite3
from datetime import date, timedelta
from pathlib import Path

from portfolio_analyzer.models import ETFHolding, ETFInfo


class CacheStore:
    def __init__(self, db_path: Path, ttl_days: int = 7):
        self.db_path = db_path
        self.ttl_days = ttl_days
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path))
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS etf_cache (
                symbol TEXT PRIMARY KEY,
                data_json TEXT NOT NULL,
                fetched_at TEXT NOT NULL
            )"""
        )
        self._conn.commit()

    def get_etf_info(self, symbol: str) -> ETFInfo | None:
        row = self._conn.execute(
            "SELECT data_json, fetched_at FROM etf_cache WHERE symbol = ?",
            (symbol,),
        ).fetchone()
        if row is None:
            return None
        fetched_at = date.fromisoformat(row[1])
        if date.today() - fetched_at > timedelta(days=self.ttl_days):
            return None
        return _deserialize(json.loads(row[0]))

    def put_etf_info(self, symbol: str, info: ETFInfo) -> None:
        data_json = json.dumps(_serialize(info))
        self._conn.execute(
            "INSERT OR REPLACE INTO etf_cache (symbol, data_json, fetched_at) VALUES (?, ?, ?)",
            (symbol, data_json, info.fetched_at.isoformat()),
        )
        self._conn.commit()

    def clear(self) -> None:
        self._conn.execute("DELETE FROM etf_cache")
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()


def _serialize(info: ETFInfo) -> dict:
    return {
        "symbol": info.symbol,
        "name": info.name,
        "expense_ratio": info.expense_ratio,
        "category": info.category,
        "family": info.family,
        "top_holdings": [
            {"symbol": h.symbol, "name": h.name, "weight": h.weight}
            for h in info.top_holdings
        ],
        "sector_weights": info.sector_weights,
        "asset_classes": info.asset_classes,
        "total_net_assets": info.total_net_assets,
        "fetched_at": info.fetched_at.isoformat(),
    }


def _deserialize(data: dict) -> ETFInfo:
    return ETFInfo(
        symbol=data["symbol"],
        name=data["name"],
        expense_ratio=data.get("expense_ratio"),
        category=data.get("category"),
        family=data.get("family"),
        top_holdings=[
            ETFHolding(symbol=h["symbol"], name=h["name"], weight=h["weight"])
            for h in data.get("top_holdings", [])
        ],
        sector_weights=data.get("sector_weights", {}),
        asset_classes=data.get("asset_classes", {}),
        total_net_assets=data.get("total_net_assets"),
        fetched_at=date.fromisoformat(data["fetched_at"]),
    )
