# data.py  –  yfinance data fetching with in-memory (L1) + Redis (L2) cache

import os
import pickle
import pandas as pd
import yfinance as yf
import redis as redis_lib
from config import TICKERS, DAILY_PERIOD, WEEKLY_PERIOD

_cache: dict[str, pd.DataFrame] = {}

_CACHE_TTL = 4 * 60 * 60  # 4 hours

_redis: redis_lib.Redis | None = None


def _get_redis() -> redis_lib.Redis | None:
    global _redis
    if _redis is not None:
        return _redis
    try:
        url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        client = redis_lib.from_url(url, decode_responses=False)
        client.ping()
        _redis = client
    except Exception:
        pass
    return _redis


def _redis_read(key: str) -> pd.DataFrame | None:
    r = _get_redis()
    if r is None:
        return None
    try:
        data = r.get(key)
        if data is None:
            return None
        return pickle.loads(data)
    except Exception:
        return None


def _redis_write(key: str, df: pd.DataFrame) -> None:
    r = _get_redis()
    if r is None:
        return
    try:
        r.setex(key, _CACHE_TTL, pickle.dumps(df))
    except Exception:
        pass


def _db_read(symbol: str, interval: str) -> pd.DataFrame | None:
    """Last-resort fallback: read OHLCV rows from PostgreSQL."""
    try:
        import db
        df = db.read_prices(symbol, interval)
        if not df.empty:
            return df
    except Exception:
        pass
    return None


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    """Flatten MultiIndex columns, strip timezone, drop empty rows."""
    if df.empty:
        return df
    if isinstance(df.columns, pd.MultiIndex):
        df = df.copy()
        df.columns = df.columns.droplevel(1)
    df.index = pd.to_datetime(df.index)
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    df.index = df.index.normalize()
    df = df[~df.index.duplicated(keep="last")]
    df.dropna(how="all", inplace=True)
    return df


def _split_batch(batch_df: pd.DataFrame, symbols: list[str]) -> dict[str, pd.DataFrame]:
    """
    Split a multi-ticker yf.download result into per-ticker DataFrames.
    yfinance returns a (Price, Ticker) MultiIndex when multiple tickers are requested.
    """
    result = {}
    if batch_df.empty:
        return result

    if isinstance(batch_df.columns, pd.MultiIndex):
        # yfinance group_by="ticker" produces MultiIndex(Ticker, Price) with ticker at level 0
        for sym in symbols:
            try:
                ticker_df = batch_df.xs(sym, axis=1, level=0).copy()
                ticker_df = _clean(ticker_df)
                if not ticker_df.empty:
                    result[sym] = ticker_df
            except KeyError:
                pass
    else:
        # Single ticker returned without MultiIndex
        if len(symbols) == 1:
            result[symbols[0]] = _clean(batch_df)

    return result


def fetch(ticker_key: str, interval: str = "1d", force: bool = False) -> pd.DataFrame:
    """Fetch a single ticker (uses cache; falls back gracefully)."""
    cache_key = f"{ticker_key}_{interval}"
    if not force and cache_key in _cache:
        return _cache[cache_key]

    symbol = TICKERS[ticker_key]
    period = WEEKLY_PERIOD if interval == "1wk" else DAILY_PERIOD
    try:
        df = yf.download(
            symbol,
            period=period,
            interval=interval,
            auto_adjust=True,
            progress=False,
        )
        df = _clean(df)
    except Exception as exc:
        print(f"[data] fetch error {symbol} ({interval}): {exc}")
        df = pd.DataFrame()

    if df.empty:
        fallback = _db_read(symbol, interval)
        if fallback is not None:
            print(f"[data] DB fallback used for {symbol} ({interval})")
            df = fallback

    _cache[cache_key] = df
    return df


def fetch_symbols_batch(symbols: list[str], interval: str = "1d") -> dict[str, pd.DataFrame]:
    """Batch-download a list of arbitrary symbols and return per-symbol DataFrames.
    Results are cached in Redis for up to 4 hours."""
    result: dict[str, pd.DataFrame] = {}
    to_fetch: list[str] = []

    for sym in symbols:
        key = f"sym_{sym}_{interval}"
        cached = _cache.get(key)
        if cached is None:
            cached = _redis_read(key)
        if cached is not None:
            _cache[key] = cached
            result[sym] = cached
        else:
            to_fetch.append(sym)

    if not to_fetch:
        return result

    period = WEEKLY_PERIOD if interval == "1wk" else DAILY_PERIOD
    try:
        batch = yf.download(
            to_fetch,
            period=period,
            interval=interval,
            auto_adjust=True,
            progress=False,
            group_by="ticker",
        )
        fetched = _split_batch(batch, to_fetch)
    except Exception as exc:
        print(f"[data] batch fetch error ({interval}): {exc}")
        fetched = {}

    for sym, df in fetched.items():
        key = f"sym_{sym}_{interval}"
        _cache[key] = df
        _redis_write(key, df)
        result[sym] = df

    # DB fallback for anything yfinance didn't return
    for sym in to_fetch:
        if sym not in result:
            fallback = _db_read(sym, interval)
            if fallback is not None:
                print(f"[data] DB fallback used for {sym} ({interval})")
                key = f"sym_{sym}_{interval}"
                _cache[key] = fallback
                result[sym] = fallback

    return result


def fetch_symbol(symbol: str, interval: str = "1d") -> pd.DataFrame:
    """Fetch any arbitrary symbol for custom ticker tabs."""
    period = WEEKLY_PERIOD if interval == "1wk" else DAILY_PERIOD
    try:
        df = yf.download(symbol, period=period, interval=interval,
                         auto_adjust=True, progress=False)
        return _clean(df)
    except Exception as exc:
        print(f"[data] fetch_symbol error {symbol} ({interval}): {exc}")
        return pd.DataFrame()


def fetch_all(interval: str = "1d", force: bool = False) -> dict[str, pd.DataFrame]:
    """
    Batch-download all configured tickers in a single yfinance request
    and split into per-ticker DataFrames. Falls back per-ticker on error.
    """
    # Check if everything is already cached
    if not force:
        cached = {key: _cache[f"{key}_{interval}"]
                  for key in TICKERS if f"{key}_{interval}" in _cache}
        if len(cached) == len(TICKERS):
            return cached

    symbols = list(TICKERS.values())
    period  = WEEKLY_PERIOD if interval == "1wk" else DAILY_PERIOD

    try:
        batch = yf.download(
            symbols,
            period=period,
            interval=interval,
            auto_adjust=True,
            progress=False,
            group_by="ticker",
        )
        per_sym = _split_batch(batch, symbols)
    except Exception as exc:
        print(f"[data] batch fetch error ({interval}): {exc}")
        per_sym = {}

    result = {}
    # Map symbol → ticker key and cache
    sym_to_key = {v: k for k, v in TICKERS.items()}
    for sym, df in per_sym.items():
        key = sym_to_key.get(sym)
        if key:
            _cache[f"{key}_{interval}"] = df
            result[key] = df

    # Fall back for any ticker that didn't come through in the batch
    for key in TICKERS:
        if key not in result:
            print(f"[data] batch miss for {key}, falling back to individual fetch")
            result[key] = fetch(key, interval, force=True)

    return result
