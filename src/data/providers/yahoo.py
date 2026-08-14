"""Yahoo Finance price provider with local JSON cache."""

from __future__ import annotations

import json
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from src.data.providers.base import (
    PriceBar,
    as_iso,
    has_forward_coverage,
    parse_iso_date,
)


CACHE_START = "2018-01-01"
DEFAULT_CACHE_DIR = Path("data/cache/yahoo")
CACHE_STALE_DAYS = 5
DOWNLOAD_PAUSE_SECONDS = 0.4


def to_yahoo_ticker(symbol: str, market: str) -> str:
    """Map a local symbol to a Yahoo Finance ticker."""
    stripped = symbol.strip().upper()
    if market == "US":
        return stripped.replace(".US", "")
    if market == "HK":
        digits = stripped.replace(".HK", "")
        if not digits.isdigit():
            raise ValueError(f"HK symbol must be numeric, got {symbol}")
        return f"{digits.zfill(4)}.HK"
    if market == "CN_A":
        code = stripped.replace(".SS", "").replace(".SZ", "")
        if code.isdigit():
            code = code.zfill(6)
        if code.startswith(("6", "9")):
            return f"{code}.SS"
        return f"{code}.SZ"
    raise ValueError(f"Unsupported market: {market}")


def _cache_path(cache_dir: Path, ticker: str) -> Path:
    """Return the JSON cache path for a ticker."""
    safe = ticker.replace("/", "_")
    return cache_dir / f"{safe}.json"


class YahooPriceProvider:
    """Fetch daily closes via yfinance and cache them locally."""

    def __init__(self, cache_dir: Path | str = DEFAULT_CACHE_DIR) -> None:
        self.cache_dir = Path(cache_dir)
        self._memory: dict[str, list[PriceBar]] = {}

    def get_price_history(
        self,
        symbol: str,
        market: str,
        start_date: str,
        end_date: str,
    ) -> list[PriceBar]:
        """Return cached or downloaded daily closes in the requested window."""
        bars = self._history_for_ticker(to_yahoo_ticker(symbol, market))
        start = parse_iso_date(start_date)
        end = parse_iso_date(end_date)
        return [bar for bar in bars if start <= parse_iso_date(bar.trading_day) <= end]

    def get_close_on_or_before(
        self,
        symbol: str,
        market: str,
        as_of_date: str,
    ) -> PriceBar | None:
        """Latest close on or before as_of_date."""
        as_of = parse_iso_date(as_of_date)
        eligible = [
            bar
            for bar in self._history_for_ticker(to_yahoo_ticker(symbol, market))
            if parse_iso_date(bar.trading_day) <= as_of
        ]
        return eligible[-1] if eligible else None

    def get_forward_close(
        self,
        symbol: str,
        market: str,
        cutoff_date: str,
        horizon_days: int,
    ) -> PriceBar | None:
        """Close on or before cutoff_date + horizon_days if that window is realized."""
        target = (parse_iso_date(cutoff_date) + timedelta(days=horizon_days)).isoformat()
        bars = self._history_for_ticker(to_yahoo_ticker(symbol, market))
        if not bars:
            return None
        if not has_forward_coverage(bars[-1].trading_day, target):
            return None
        cutoff_bar = self.get_close_on_or_before(symbol, market, cutoff_date)
        target_bar = self.get_close_on_or_before(symbol, market, target)
        if cutoff_bar is None or target_bar is None:
            return None
        if parse_iso_date(target_bar.trading_day) <= parse_iso_date(cutoff_bar.trading_day):
            return None
        return target_bar

    def _history_for_ticker(self, ticker: str) -> list[PriceBar]:
        """Load ticker history from cache, downloading if needed or stale."""
        if ticker in self._memory:
            return self._memory[ticker]
        path = _cache_path(self.cache_dir, ticker)
        cached = self._read_cache(path)
        if cached and not self._is_stale(cached):
            self._memory[ticker] = cached
            return cached

        try:
            bars = self._download(ticker)
        except Exception:
            if cached:
                self._memory[ticker] = cached
                return cached
            raise

        self._write_cache(path, bars)
        self._memory[ticker] = bars
        return bars

    def _read_cache(self, path: Path) -> list[PriceBar]:
        """Load cached bars, or an empty list if missing/invalid."""
        if not path.exists():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
        return [PriceBar(trading_day=row["trading_day"], close=float(row["close"])) for row in payload]

    def _write_cache(self, path: Path, bars: list[PriceBar]) -> None:
        """Persist bars as JSON."""
        path.parent.mkdir(parents=True, exist_ok=True)
        serialized: list[dict[str, Any]] = [
            {"trading_day": bar.trading_day, "close": bar.close} for bar in bars
        ]
        path.write_text(json.dumps(serialized, ensure_ascii=False), encoding="utf-8")

    def _is_stale(self, bars: list[PriceBar]) -> bool:
        """Refresh cache when the last bar is older than CACHE_STALE_DAYS."""
        if not bars:
            return True
        last = parse_iso_date(bars[-1].trading_day)
        return (date.today() - last).days > CACHE_STALE_DAYS

    def _download(self, ticker: str) -> list[PriceBar]:
        """Download daily history from Yahoo Finance."""
        try:
            import yfinance as yf
        except ImportError as exc:
            raise ImportError("yfinance is required. Install with: pip install yfinance") from exc

        frame = yf.download(
            ticker,
            start=CACHE_START,
            auto_adjust=False,
            progress=False,
            threads=False,
        )
        if frame is None or frame.empty:
            raise ValueError(f"Yahoo returned no history for {ticker}")

        series = _close_series(frame, ticker)
        bars: list[PriceBar] = []
        for index, close_value in series.items():
            if close_value is None:
                continue
            try:
                close = float(close_value)
            except (TypeError, ValueError):
                continue
            if close != close:  # NaN
                continue
            bars.append(PriceBar(trading_day=as_iso(index), close=round(close, 6)))
        if not bars:
            raise ValueError(f"Yahoo history for {ticker} had no usable closes")
        time.sleep(DOWNLOAD_PAUSE_SECONDS)
        return bars


def _close_series(frame: Any, ticker: str) -> Any:
    """Extract a single Close series from a yfinance DataFrame."""
    if getattr(frame.columns, "nlevels", 1) > 1:
        close_frame = frame["Close"]
        if hasattr(close_frame, "columns"):
            if ticker in close_frame.columns:
                return close_frame[ticker]
            return close_frame.iloc[:, 0]
        return close_frame
    if "Close" in frame.columns:
        return frame["Close"]
    return frame.iloc[:, 0]
