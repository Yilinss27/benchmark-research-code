"""Yahoo financial statements and earnings with local JSON cache.

Yahoo quarterly statements only keep ~5 recent periods. Older cutoffs fall
back to annual statements. Periods are treated as public only after a reporting lag
so we do not treat an unreleased filing as available at cutoff.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from src.data.providers.base import add_calendar_days, as_iso, parse_iso_date
from src.data.providers.yahoo import DOWNLOAD_PAUSE_SECONDS, to_yahoo_ticker


DEFAULT_CACHE_DIR = Path("data/cache/yahoo")
QUARTER_LAG_DAYS = 45
ANNUAL_LAG_DAYS = 100

REVENUE_KEYS = ("Operating Revenue", "Total Revenue")
NET_INCOME_KEYS = (
    "Net Income",
    "Net Income Common Stockholders",
    "Net Income From Continuing Operation Net Minority Interest",
)
GROSS_PROFIT_KEYS = ("Gross Profit",)
SHARES_KEYS = ("Diluted Average Shares", "Basic Average Shares", "Ordinary Shares Number", "Share Issued")
EQUITY_KEYS = ("Stockholders Equity", "Common Stock Equity", "Tangible Book Value")
DEBT_KEYS = ("Total Debt",)


def _safe_ticker(ticker: str) -> str:
    return ticker.replace("/", "_")


def _frame_to_nested(frame: Any) -> dict[str, dict[str, float]]:
    """Convert a yfinance statement DataFrame to {period: {row: value}}."""
    nested: dict[str, dict[str, float]] = {}
    if frame is None or getattr(frame, "empty", True):
        return nested
    for column in frame.columns:
        period = as_iso(column)
        row_map: dict[str, float] = {}
        for index in frame.index:
            value = frame.loc[index, column]
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            if number != number:
                continue
            row_map[str(index)] = number
        if row_map:
            nested[period] = row_map
    return nested


class YahooFundamentals:
    """Historical fundamentals with modeled publication lags (not true PIT)."""

    source_tier = "yahoo_lagged_research_only"

    def __init__(self, cache_dir: Path | str = DEFAULT_CACHE_DIR) -> None:
        self.cache_dir = Path(cache_dir)
        self._statement_memory: dict[str, dict[str, Any]] = {}
        self._earnings_memory: dict[str, list[dict[str, Any]]] = {}

    def statements(self, symbol: str, market: str) -> dict[str, Any]:
        """Return cached income/balance nested dicts for a ticker."""
        ticker = to_yahoo_ticker(symbol, market)
        if ticker in self._statement_memory:
            return self._statement_memory[ticker]
        path = self.cache_dir / "statements" / f"{_safe_ticker(ticker)}.json"
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            self._statement_memory[ticker] = payload
            return payload

        try:
            import yfinance as yf
        except ImportError as exc:
            raise ImportError("yfinance is required. Install with: pip install yfinance") from exc

        handle = yf.Ticker(ticker)
        payload = {
            "ticker": ticker,
            "income_q": _nested_statement(handle, "get_income_stmt", "quarterly", "quarterly_income_stmt"),
            "income_y": _nested_statement(handle, "get_income_stmt", "yearly", "income_stmt"),
            "balance_q": _nested_statement(handle, "get_balance_sheet", "quarterly", "quarterly_balance_sheet"),
            "balance_y": _nested_statement(handle, "get_balance_sheet", "yearly", "balance_sheet"),
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        time.sleep(DOWNLOAD_PAUSE_SECONDS)
        self._statement_memory[ticker] = payload
        return payload

    def earnings_events(self, symbol: str, market: str) -> list[dict[str, Any]]:
        """Return earnings dates with EPS estimate/actual/surprise when available."""
        ticker = to_yahoo_ticker(symbol, market)
        if ticker in self._earnings_memory:
            return self._earnings_memory[ticker]
        path = self.cache_dir / "earnings" / f"{_safe_ticker(ticker)}.json"
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            self._earnings_memory[ticker] = payload
            return payload

        try:
            import yfinance as yf
        except ImportError as exc:
            raise ImportError("yfinance is required. Install with: pip install yfinance") from exc

        handle = yf.Ticker(ticker)
        try:
            frame = handle.get_earnings_dates(limit=40)
        except Exception:
            frame = None
        events: list[dict[str, Any]] = []
        if frame is not None and not frame.empty:
            for index, row in frame.iterrows():
                reported = _optional_float(row.get("Reported EPS"))
                estimate = _optional_float(row.get("EPS Estimate"))
                surprise = _optional_float(row.get("Surprise(%)"))
                events.append(
                    {
                        "event_date": as_iso(index),
                        "reported_eps": reported,
                        "eps_estimate": estimate,
                        "surprise_pct": surprise,
                    }
                )
        events.sort(key=lambda item: item["event_date"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(events, ensure_ascii=False), encoding="utf-8")
        time.sleep(DOWNLOAD_PAUSE_SECONDS)
        self._earnings_memory[ticker] = events
        return events

    def fundamentals_snapshot(
        self,
        symbol: str,
        market: str,
        cutoff_date: str,
        price: float,
    ) -> dict[str, Any] | None:
        """Build an A2-style valuation snapshot as of cutoff_date."""
        stmts = self.statements(symbol, market)
        bundle = _ttm_or_annual(stmts, cutoff_date)
        if bundle is None:
            return None
        shares = bundle["shares"]
        net_income = bundle["net_income"]
        revenue = bundle["revenue"]
        equity = bundle["equity"]
        debt = bundle["debt"]
        pe = _ratio(price, _per_share(net_income, shares))
        pb = _ratio(price, _per_share(equity, shares))
        ps = _ratio(price * shares if shares else None, revenue)
        debt_to_market = _ratio(debt, price * shares if shares else None)
        return {
            "price": round(price, 6),
            "pe": _round(pe),
            "pb": _round(pb),
            "peg": None,
            "ps": _round(ps),
            "dividend_ratio": None,
            "ev_excluding_cash": None,
            "debt_to_market_cap": _round(debt_to_market),
            "pcf_operating": None,
            "trading_day": cutoff_date,
            "statement_freq": bundle["freq"],
            "statement_period": bundle["period"],
        }

    def metric_pair(
        self,
        symbol: str,
        market: str,
        cutoff_date: str,
        metric_name: str,
    ) -> dict[str, Any] | None:
        """Return historical and next-period values for a C-task metric."""
        stmts = self.statements(symbol, market)
        pair = _history_future_periods(stmts, cutoff_date, metric_name)
        if pair is None:
            return None
        return pair


def _nested_statement(handle: Any, method_name: str, freq: str, legacy_attr: str) -> dict[str, dict[str, float]]:
    """Load one Yahoo statement table, falling back to a legacy ticker attribute."""
    method = getattr(handle, method_name, None)
    if callable(method):
        try:
            return _frame_to_nested(method(freq=freq))
        except TypeError:
            try:
                return _frame_to_nested(method())
            except Exception:
                pass
        except Exception:
            pass
    return _frame_to_nested(getattr(handle, legacy_attr, None))


def _optional_float(value: Any) -> float | None:
    """Parse a numeric cell, treating NaN as missing."""
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return number


def _round(value: float | None, digits: int = 6) -> float | None:
    """Round a ratio when present."""
    if value is None:
        return None
    return round(value, digits)


def _ratio(numer: float | None, denom: float | None) -> float | None:
    """Safe division."""
    if numer is None or denom is None or denom == 0:
        return None
    return numer / denom


def _per_share(total: float | None, shares: float | None) -> float | None:
    """Convert a totals figure to per-share."""
    return _ratio(total, shares)


def _normalize_key(key: str) -> str:
    """Normalize statement row labels for Yahoo camelCase vs spaced names."""
    return key.replace(" ", "").replace("_", "").lower()


def _cell(row: dict[str, float], keys: tuple[str, ...]) -> float | None:
    """First matching key in a statement row map."""
    normalized = {_normalize_key(name): value for name, value in row.items()}
    for key in keys:
        value = normalized.get(_normalize_key(key))
        if value is not None:
            return value
    return None


def _public_periods(table: dict[str, dict[str, float]], cutoff_date: str, lag_days: int) -> list[str]:
    """Periods whose filing lag has elapsed by cutoff_date."""
    eligible: list[str] = []
    for period in table:
        available = add_calendar_days(period, lag_days)
        if parse_iso_date(available) <= parse_iso_date(cutoff_date):
            eligible.append(period)
    return sorted(eligible)


def _ttm_or_annual(stmts: dict[str, Any], cutoff_date: str) -> dict[str, Any] | None:
    """TTM from last 4 complete public quarters, else last public annual."""
    income_q = stmts.get("income_q") or {}
    balance_q = stmts.get("balance_q") or {}
    q_periods = _public_periods(income_q, cutoff_date, QUARTER_LAG_DAYS)
    if len(q_periods) >= 4:
        last4 = q_periods[-4:]
        latest = last4[-1]
        revenue = _sum_cells(income_q, last4, REVENUE_KEYS)
        net_income = _sum_cells(income_q, last4, NET_INCOME_KEYS)
        shares = _cell(income_q.get(latest, {}), SHARES_KEYS) or _cell(
            balance_q.get(latest, {}), SHARES_KEYS
        )
        equity = _cell(balance_q.get(latest, {}), EQUITY_KEYS)
        debt = _cell(balance_q.get(latest, {}), DEBT_KEYS)
        if shares is None:
            shares = _latest_public_cell(stmts, cutoff_date, SHARES_KEYS)
        if equity is None:
            equity = _latest_public_cell(stmts, cutoff_date, EQUITY_KEYS)
        if debt is None:
            debt = _latest_public_cell(stmts, cutoff_date, DEBT_KEYS)
        if (revenue is not None or net_income is not None) and shares is not None:
            return {
                "freq": "quarterly_ttm",
                "period": latest,
                "revenue": revenue,
                "net_income": net_income,
                "shares": shares,
                "equity": equity,
                "debt": debt,
            }

    income_y = stmts.get("income_y") or {}
    balance_y = stmts.get("balance_y") or {}
    y_periods = _public_periods(income_y, cutoff_date, ANNUAL_LAG_DAYS)
    if not y_periods:
        return None
    latest = y_periods[-1]
    row = income_y.get(latest, {})
    bal = balance_y.get(latest, {})
    return {
        "freq": "annual",
        "period": latest,
        "revenue": _cell(row, REVENUE_KEYS),
        "net_income": _cell(row, NET_INCOME_KEYS),
        "shares": _cell(row, SHARES_KEYS) or _cell(bal, SHARES_KEYS),
        "equity": _cell(bal, EQUITY_KEYS),
        "debt": _cell(bal, DEBT_KEYS),
    }


def _latest_public_cell(stmts: dict[str, Any], cutoff_date: str, keys: tuple[str, ...]) -> float | None:
    """Latest public statement cell matching keys, preferring quarterly then annual."""
    for table, lag in (
        (stmts.get("income_q") or {}, QUARTER_LAG_DAYS),
        (stmts.get("balance_q") or {}, QUARTER_LAG_DAYS),
        (stmts.get("income_y") or {}, ANNUAL_LAG_DAYS),
        (stmts.get("balance_y") or {}, ANNUAL_LAG_DAYS),
    ):
        for period in reversed(_public_periods(table, cutoff_date, lag)):
            value = _cell(table.get(period, {}), keys)
            if value is not None:
                return value
    return None


def _sum_cells(table: dict[str, dict[str, float]], periods: list[str], keys: tuple[str, ...]) -> float | None:
    """Sum a statement line across periods; require every period to have the line."""
    total = 0.0
    for period in periods:
        value = _cell(table.get(period, {}), keys)
        if value is None:
            return None
        total += value
    return total


def _history_future_periods(
    stmts: dict[str, Any],
    cutoff_date: str,
    metric_name: str,
) -> dict[str, Any] | None:
    """Last public period with data as of cutoff, plus the next not-yet-public period."""
    cutoff = parse_iso_date(cutoff_date)
    for freq, table, lag in (
        ("quarterly", stmts.get("income_q") or {}, QUARTER_LAG_DAYS),
        ("annual", stmts.get("income_y") or {}, ANNUAL_LAG_DAYS),
    ):
        public = _public_periods(table, cutoff_date, lag)
        all_periods = sorted(table.keys())
        historical = None
        historical_value = None
        for period in reversed(public):
            value = _metric_value(table.get(period, {}), metric_name)
            if value is not None:
                historical = period
                historical_value = value
                break
        if historical is None:
            continue
        for future in all_periods:
            if future <= historical:
                continue
            future_value = _metric_value(table.get(future, {}), metric_name)
            if future_value is None:
                continue
            if parse_iso_date(add_calendar_days(future, lag)) <= cutoff:
                continue
            return {
                "freq": freq,
                "report_period_historical": historical,
                "report_period_future": future,
                "historical_value": historical_value,
                "future_value": future_value,
            }
    return None


def _metric_value(row: dict[str, float], metric_name: str) -> float | None:
    """Map C metric names onto Yahoo income-statement rows."""
    if metric_name == "operating_revenue":
        return _cell(row, REVENUE_KEYS)
    if metric_name == "net_profit":
        return _cell(row, NET_INCOME_KEYS)
    if metric_name == "gross_margin":
        revenue = _cell(row, REVENUE_KEYS)
        gross = _cell(row, GROSS_PROFIT_KEYS)
        ratio = _ratio(gross, revenue)
        return None if ratio is None else round(ratio * 100.0, 6)
    if metric_name == "net_margin":
        revenue = _cell(row, REVENUE_KEYS)
        net_income = _cell(row, NET_INCOME_KEYS)
        ratio = _ratio(net_income, revenue)
        return None if ratio is None else round(ratio * 100.0, 6)
    raise ValueError(f"Unsupported C metric: {metric_name}")
