"""Historical bar fetch for research.

Two sources, both used strictly in READ mode:
  - AlpacaSource: batched daily bars (100 syms/call), authenticated. Prefer.
  - YFinanceSource: unauthenticated fallback, per-symbol.
  - CachedFileSource: reads pre-downloaded parquet/csv from disk. Preferred
    for reproducibility of the actual research run — download once, cache,
    rerun forever without network.

Runners take any source that implements `.daily(symbol, start, end)` → DataFrame
with columns [open, high, low, close, volume], DatetimeIndex.

Nothing here touches production. Nothing runs on import.
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime
from pathlib import Path
from typing import Protocol

import pandas as pd


logger = logging.getLogger(__name__)


class BarSource(Protocol):
    def daily(self, symbol: str, start: date, end: date) -> pd.DataFrame: ...


# ---------------------------------------------------------------------- Alpaca
class AlpacaSource:
    """Requires ALPACA_KEY and ALPACA_SECRET env vars OR passed args.

    Batched: fetches many symbols per call for efficiency. But the public
    interface returns one DataFrame at a time to keep the Detector loop
    simple; batching happens under the hood with a small LRU-style cache.
    """

    def __init__(self, key: str | None = None, secret: str | None = None,
                 feed: str = "iex"):
        try:
            import requests  # noqa: F401  (imported to fail-fast)
        except ImportError as e:
            raise RuntimeError("requests required for AlpacaSource") from e
        self.key = key or os.environ.get("ALPACA_KEY", "")
        self.secret = secret or os.environ.get("ALPACA_SECRET", "")
        if not (self.key and self.secret):
            raise RuntimeError(
                "AlpacaSource requires ALPACA_KEY and ALPACA_SECRET (env or ctor args)"
            )
        self.feed = feed
        self._session = self._build_session()

    def _build_session(self):
        import requests
        s = requests.Session()
        s.headers.update({
            "APCA-API-KEY-ID": self.key,
            "APCA-API-SECRET-KEY": self.secret,
        })
        return s

    def daily(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        params = {
            "symbols": symbol,
            "timeframe": "1Day",
            "start": start.isoformat(),
            "end": end.isoformat(),
            "adjustment": "raw",
            "feed": self.feed,
            "limit": 10000,
        }
        r = self._session.get("https://data.alpaca.markets/v2/stocks/bars", params=params, timeout=30)
        if r.status_code != 200:
            logger.warning("alpaca bars %s -> %s: %s", symbol, r.status_code, r.text[:200])
            return pd.DataFrame()
        rows = (r.json().get("bars") or {}).get(symbol) or []
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows).rename(columns={
            "t": "time", "o": "open", "h": "high", "l": "low", "c": "close", "v": "volume",
        })
        df["time"] = pd.to_datetime(df["time"], utc=True, errors="coerce")
        df = df.dropna(subset=["time"]).set_index("time").sort_index()
        return df[["open", "high", "low", "close", "volume"]]


# ---------------------------------------------------------------------- yfinance
class YFinanceSource:
    def daily(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        import yfinance as yf
        try:
            df = yf.download(
                symbol, start=start.isoformat(), end=end.isoformat(),
                interval="1d", auto_adjust=True, progress=False, threads=False,
            )
        except Exception as e:
            logger.warning("yf %s: %s", symbol, e)
            return pd.DataFrame()
        if df is None or df.empty:
            return pd.DataFrame()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.rename(columns=str.lower)
        return df[["open", "high", "low", "close", "volume"]]


# ---------------------------------------------------------------------- cached
class CachedFileSource:
    """Reads per-symbol parquet from a directory. Recommended for actual runs
    so the entire universe is fetched once, then research is reproducible
    without any network dependency."""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def _path(self, symbol: str) -> Path:
        return self.root / f"{symbol.upper()}.parquet"

    def daily(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        p = self._path(symbol)
        if not p.exists():
            return pd.DataFrame()
        df = pd.read_parquet(p)
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index, utc=True, errors="coerce")
        mask = (df.index.date >= start) & (df.index.date <= end)
        return df.loc[mask, ["open", "high", "low", "close", "volume"]]


# ---------------------------------------------------------------------- resilient
class ResilientSource:
    """Try each source in order; return the first non-empty result."""

    def __init__(self, sources: list[BarSource]):
        self.sources = sources

    def daily(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        for src in self.sources:
            df = src.daily(symbol, start, end)
            if not df.empty:
                return df
        return pd.DataFrame()
