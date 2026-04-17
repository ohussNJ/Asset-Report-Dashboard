# api.py  –  FastAPI backend

import asyncio
import math
import os
import pathlib
from contextlib import asynccontextmanager
from typing import Any

import numpy as np
import pandas as pd
import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from pydantic import BaseModel

import json

import data as Data
import db
import divergence as Div
import indicators
import signals as Sig
import backtest as BT
from config import TICKERS, WATCHLIST, STOCHRSI_CONFIGS


# ── JSON serialization ─────────────────────────────────────────────────────────

def _sanitize(val: Any) -> Any:
    """Recursively convert numpy scalars and NaN to JSON-safe Python types."""
    if isinstance(val, float) and math.isnan(val):
        return None
    if isinstance(val, np.floating):
        f = float(val)
        return None if math.isnan(f) else f
    if isinstance(val, np.integer):
        return int(val)
    if isinstance(val, np.bool_):
        return bool(val)
    if isinstance(val, dict):
        return {k: _sanitize(v) for k, v in val.items()}
    if isinstance(val, list):
        return [_sanitize(i) for i in val]
    return val


def _clean(d: dict) -> dict:
    return {k: _sanitize(v) for k, v in d.items()}


# ── TradingView data formatters ────────────────────────────────────────────────

def _tv_line(series: pd.Series) -> list[dict]:
    out = []
    for dt, val in series.items():
        if pd.isna(val):
            continue
        out.append({"time": pd.Timestamp(dt).strftime("%Y-%m-%d"), "value": float(val)})
    return out


def _tv_candles(df: pd.DataFrame) -> list[dict]:
    out = []
    for dt, row in df[["Open", "High", "Low", "Close", "Volume"]].iterrows():
        try:
            out.append({
                "time":   pd.Timestamp(dt).strftime("%Y-%m-%d"),
                "open":   float(row["Open"]),
                "high":   float(row["High"]),
                "low":    float(row["Low"]),
                "close":  float(row["Close"]),
                "volume": float(row["Volume"]) if not pd.isna(row["Volume"]) else 0.0,
            })
        except Exception:
            pass
    return out


# ── WebSocket connection manager ───────────────────────────────────────────────

class _WSManager:
    def __init__(self) -> None:
        self._sockets: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._sockets.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self._sockets:
            self._sockets.remove(ws)

    async def broadcast(self, msg: str) -> None:
        for ws in list(self._sockets):
            try:
                await ws.send_text(msg)
            except Exception:
                self.disconnect(ws)


_ws = _WSManager()


# ── Watchlist persistence ──────────────────────────────────────────────────────

_CUSTOM_WL_PATH = pathlib.Path(__file__).parent / "watchlist_custom.json"

def _load_custom_wl() -> dict[str, dict[str, str]]:
    if _CUSTOM_WL_PATH.exists():
        with open(_CUSTOM_WL_PATH) as f:
            return json.load(f)
    return {}

def _save_custom_wl(custom: dict[str, dict[str, str]]) -> None:
    with open(_CUSTOM_WL_PATH, "w") as f:
        json.dump(custom, f, indent=2)

def _merged_wl() -> dict[str, dict[str, str]]:
    merged: dict[str, dict[str, str]] = {cat: dict(entries) for cat, entries in WATCHLIST.items()}
    for cat, entries in _load_custom_wl().items():
        merged.setdefault(cat, {}).update(entries)
    return merged


# ── App state ──────────────────────────────────────────────────────────────────

_daily:      dict[str, pd.DataFrame] = {}
_weekly:     dict[str, pd.DataFrame] = {}
_comp_d:     dict[str, pd.DataFrame] = {}   # indicators computed on daily bars
_comp_w:     dict[str, pd.DataFrame] = {}   # indicators computed on weekly bars
_wl_daily:   dict[str, pd.DataFrame] = {}
_wl_weekly:  dict[str, pd.DataFrame] = {}
_wl_comp_d:  dict[str, pd.DataFrame] = {}  # pre-computed indicators for watchlist-only tickers
_wl_comp_w:  dict[str, pd.DataFrame] = {}
_sig_d:      dict[str, dict] = {}           # pre-computed signals (daily) for all symbols
_sig_w:      dict[str, dict] = {}           # pre-computed signals (weekly) for all symbols
_custom_syms: set[str] = set()             # user-added tickers (survive refreshes)


def _compute_sig_cache() -> None:
    """Recompute _sig_d / _sig_w from all available comp DataFrames."""
    global _sig_d, _sig_w
    _sig_d = {}
    _sig_w = {}
    for name, df in _comp_d.items():
        if not df.empty:
            try:
                _sig_d[name] = _clean(Sig.get_signals(df))
            except Exception:
                pass
    for name, df in _comp_w.items():
        if not df.empty:
            try:
                _sig_w[name] = _clean(Sig.get_signals(df))
            except Exception:
                pass
    for sym, df in _wl_comp_d.items():
        if not df.empty and sym not in _sig_d:
            try:
                _sig_d[sym] = _clean(Sig.get_signals(df))
            except Exception:
                pass
    for sym, df in _wl_comp_w.items():
        if not df.empty and sym not in _sig_w:
            try:
                _sig_w[sym] = _clean(Sig.get_signals(df))
            except Exception:
                pass


def _load_all() -> None:
    global _daily, _weekly, _comp_d, _comp_w, _wl_daily, _wl_weekly, _wl_comp_d, _wl_comp_w

    _daily  = Data.fetch_all("1d",  force=True)
    _weekly = Data.fetch_all("1wk", force=True)

    _comp_d = {}
    _comp_w = {}
    for name in TICKERS:
        dd = _daily.get(name)
        dw = _weekly.get(name)
        if dd is None or dd.empty:
            continue
        fallback = dw if (dw is not None and not dw.empty) else dd
        _comp_d[name] = indicators.compute_all(dd, fallback)
        if dw is not None and not dw.empty:
            _comp_w[name] = indicators.compute_all(dw, dw)

    # Re-fetch any user-added custom tickers so they survive a scheduled refresh
    for sym in list(_custom_syms):
        dd = Data.fetch_symbol(sym, "1d")
        dw = Data.fetch_symbol(sym, "1wk")
        if dd.empty:
            continue
        fallback = dw if not dw.empty else dd
        _comp_d[sym] = indicators.compute_all(dd, fallback)
        if not dw.empty:
            _comp_w[sym] = indicators.compute_all(dw, dw)

    main_syms = set(TICKERS.keys()) | _custom_syms
    all_syms  = [s for entries in _merged_wl().values() for s in entries if s not in main_syms]
    _wl_daily  = Data.fetch_symbols_batch(all_syms, "1d")
    _wl_weekly = Data.fetch_symbols_batch(all_syms, "1wk")

    _wl_comp_d = {}
    _wl_comp_w = {}
    for sym in all_syms:
        dd = _wl_daily.get(sym)
        dw = _wl_weekly.get(sym)
        if dd is None or dd.empty:
            continue
        fallback = dw if (dw is not None and not dw.empty) else dd
        _wl_comp_d[sym] = indicators.compute_all(dd, fallback)
        if dw is not None and not dw.empty:
            _wl_comp_w[sym] = indicators.compute_all(dw, dw)

    _compute_sig_cache()


async def _redis_listener() -> None:
    """Subscribe to worker channels and forward events to WebSocket clients."""
    url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    try:
        r      = aioredis.from_url(url)
        pubsub = r.pubsub()
        await pubsub.subscribe("asset_report:refresh", "asset_report:alerts")
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            channel = message["channel"]
            if isinstance(channel, bytes):
                channel = channel.decode()
            if channel == "asset_report:refresh":
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, _load_all)
                await _ws.broadcast("refresh")
            elif channel == "asset_report:alerts":
                data = message["data"]
                if isinstance(data, bytes):
                    data = data.decode()
                await _ws.broadcast(f"alert:{data}")
    except Exception as exc:
        print(f"[api] redis listener stopped: {exc}")


# ── Lifespan ───────────────────────────────────────────────────────────────────

@asynccontextmanager
async def _lifespan(app: FastAPI):
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, db.init_db)
    await loop.run_in_executor(None, _load_all)
    task = asyncio.create_task(_redis_listener())
    yield
    task.cancel()


app = FastAPI(title="Asset Report", lifespan=_lifespan)


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/api/tickers")
def get_tickers(interval: str = Query("1d", pattern="^(1d|1wk)$")) -> JSONResponse:
    src = _sig_d if interval == "1d" else _sig_w
    comp_src = _comp_d if interval == "1d" else _comp_w
    result = {name: sig for name, sig in src.items() if name in comp_src}
    return JSONResponse(result)


@app.post("/api/custom-ticker/{sym}")
def add_custom_ticker(sym: str) -> JSONResponse:
    sym = sym.strip().upper()
    if sym in TICKERS or sym in _custom_syms:
        return JSONResponse({"ok": True, "symbol": sym})

    dd = Data.fetch_symbol(sym, "1d")
    if dd.empty:
        raise HTTPException(404, f"No data found for '{sym}', check the symbol")

    dw = Data.fetch_symbol(sym, "1wk")
    fallback = dw if not dw.empty else dd
    _comp_d[sym] = indicators.compute_all(dd, fallback)
    if not dw.empty:
        _comp_w[sym] = indicators.compute_all(dw, dw)
    _custom_syms.add(sym)
    try:
        _sig_d[sym] = _clean(Sig.get_signals(_comp_d[sym]))
    except Exception:
        pass
    if sym in _comp_w:
        try:
            _sig_w[sym] = _clean(Sig.get_signals(_comp_w[sym]))
        except Exception:
            pass
    return JSONResponse({"ok": True, "symbol": sym})


def _divergences(df: pd.DataFrame, indicator_col: str,
                 min_price_pct: float = 0.3, min_ind_delta: float = 3.0) -> list:
    if indicator_col not in df.columns:
        return []
    close_s = df["Close"].dropna()
    ind_s   = df[indicator_col].dropna()
    common  = close_s.index.intersection(ind_s.index)
    if len(common) < 20:
        return []
    price_a = close_s.loc[common].values.astype(float)
    ind_a   = ind_s.loc[common].values.astype(float)
    dates   = common
    try:
        divs = Div.find_regular_divergences(price_a, ind_a,
                                            min_price_pct=min_price_pct,
                                            min_ind_delta=min_ind_delta)
    except Exception:
        return []
    out = []
    for d in divs:
        try:
            out.append({
                "type":     d["type"],
                "price_t1": pd.Timestamp(dates[d["pi1"]]).strftime("%Y-%m-%d"),
                "price_t2": pd.Timestamp(dates[d["pi2"]]).strftime("%Y-%m-%d"),
                "price_v1": float(d["p1"]),
                "price_v2": float(d["p2"]),
                "ind_t1":   pd.Timestamp(dates[d["ii1"]]).strftime("%Y-%m-%d"),
                "ind_t2":   pd.Timestamp(dates[d["ii2"]]).strftime("%Y-%m-%d"),
                "ind_v1":   float(d["ind1"]),
                "ind_v2":   float(d["ind2"]),
            })
        except (IndexError, KeyError):
            pass
    return out


@app.get("/api/tickers/{sym}/indicators")
def get_indicators(sym: str, interval: str = Query("1d", pattern="^(1d|1wk)$")) -> JSONResponse:
    if sym not in TICKERS and sym not in _custom_syms:
        raise HTTPException(404, f"Unknown ticker: {sym}")

    src = _comp_d if interval == "1d" else _comp_w
    df  = src.get(sym)
    if df is None or df.empty:
        raise HTTPException(503, "No data available")

    def col(name: str) -> list[dict]:
        return _tv_line(df[name].dropna()) if name in df.columns else []

    payload: dict[str, Any] = {
        "candles":  _tv_candles(df),
        "ema50":    col("EMA_50"),
        "ema100":   col("EMA_100"),
        "ema200":   col("EMA_200"),
        "sma50":    col("SMA_50"),
        "sma100":   col("SMA_100"),
        "sma200":   col("SMA_200"),
        "kc_upper": col("KC_UPPER"),
        "kc_basis": col("KC_BASIS"),
        "kc_lower": col("KC_LOWER"),
        "nw":       col("NW"),
        "nw_upper": col("NW_UPPER"),
        "nw_lower": col("NW_LOWER"),
        "bull_sma": col("BULL_SMA"),
        "bull_ema": col("BULL_EMA"),
        "rsi":      col("RSI"),
        "rsi_ma":   col("RSI_MA"),
        "obv":      col("OBV"),
        "obv_ma":   col("OBV_MA"),
        "vol_ma":   col("VOL_MA"),
        "score":    _tv_line(Sig.score_history(df, n=len(df))),
    }

    for i, cfg in enumerate(STOCHRSI_CONFIGS):
        lbl = cfg["label"]
        payload[f"srsi_k_{i}"] = col(f"SRSI_{lbl}_K")
        payload[f"srsi_d_{i}"] = col(f"SRSI_{lbl}_D")

    # CNV histogram
    payload["cnv"] = col("CNV_TB")

    # Keltner reference prices (17-bar and 42-bar lookback)
    close_s = df["Close"].dropna()
    payload["price_17"] = float(close_s.iloc[-17]) if len(close_s) >= 17 else None
    payload["price_42"] = float(close_s.iloc[-42]) if len(close_s) >= 42 else None

    # Divergences for RSI OBV and Score
    payload["div_rsi"]   = _divergences(df, "RSI", min_ind_delta=2.0)
    obv_arr = df["OBV"].dropna().values.astype(float) if "OBV" in df.columns else np.array([])
    obv_delta = max(float(np.nanmax(obv_arr) - np.nanmin(obv_arr)) * 0.01, 1.0) if len(obv_arr) else 1.0
    payload["div_obv"]   = _divergences(df, "OBV", min_ind_delta=obv_delta)
    score_s = Sig.score_history(df, n=len(df))
    df_tmp  = df.copy()
    df_tmp["_SCORE"] = score_s
    payload["div_score"] = _divergences(df_tmp, "_SCORE", min_ind_delta=3.0)

    return JSONResponse(payload)


@app.get("/api/watchlist")
def get_watchlist(interval: str = Query("1d", pattern="^(1d|1wk)$")) -> JSONResponse:
    sig_src = _sig_d if interval == "1d" else _sig_w

    # Map TICKERS symbol -> signal (e.g. "BTC-USD" -> sig) for watchlist overlap
    ticker_sym_sigs: dict[str, dict] = {}
    for name in TICKERS:
        sym = TICKERS[name]
        if name in sig_src:
            ticker_sym_sigs[sym] = sig_src[name]

    result: dict[str, list] = {}
    for category, entries in _merged_wl().items():
        rows = []
        for sym, label in entries.items():
            sig = ticker_sym_sigs.get(sym) or sig_src.get(sym)
            if sig is None:
                continue
            rows.append({"symbol": sym, "name": label, **sig})
        result[category] = rows

    return JSONResponse(result)


class WatchlistAddRequest(BaseModel):
    symbol:   str
    name:     str
    category: str

@app.post("/api/watchlist/add")
def add_watchlist_item(req: WatchlistAddRequest) -> JSONResponse:
    sym = req.symbol.strip().upper()
    name = req.name.strip()
    category = req.category.strip()
    if not sym or not name or not category:
        raise HTTPException(400, "symbol, name, and category are required")

    # Reject if already in static config
    for entries in WATCHLIST.values():
        if sym in entries:
            raise HTTPException(409, f"{sym} is already in the watchlist")

    custom = _load_custom_wl()
    for entries in custom.values():
        if sym in entries:
            raise HTTPException(409, f"{sym} is already in the watchlist")

    custom.setdefault(category, {})[sym] = name
    _save_custom_wl(custom)

    # Fetch + compute indicators for the new symbol so it shows immediately
    dd = Data.fetch_symbols_batch([sym], "1d").get(sym)
    dw = Data.fetch_symbols_batch([sym], "1wk").get(sym)
    if dd is not None and not dd.empty:
        _wl_daily[sym]  = dd
        fallback = dw if (dw is not None and not dw.empty) else dd
        _wl_comp_d[sym] = indicators.compute_all(dd, fallback)
        if dw is not None and not dw.empty:
            _wl_weekly[sym]  = dw
            _wl_comp_w[sym]  = indicators.compute_all(dw, dw)
        try:
            _sig_d[sym] = _clean(Sig.get_signals(_wl_comp_d[sym]))
        except Exception:
            pass
        if sym in _wl_comp_w:
            try:
                _sig_w[sym] = _clean(Sig.get_signals(_wl_comp_w[sym]))
            except Exception:
                pass

    return JSONResponse({"ok": True, "symbol": sym, "category": category})



@app.get("/api/watchlist/categories")
def get_watchlist_categories() -> JSONResponse:
    return JSONResponse(list(_merged_wl().keys()))


@app.get("/api/backtest/{sym}")
def get_backtest(
    sym:        str,
    entry:      int = Query(30, ge=1,  le=100),
    exit_th:    int = Query(10, ge=0,  le=50),
    slope_bars: int = Query(5,  ge=2,  le=20),
) -> JSONResponse:
    if sym not in TICKERS:
        raise HTTPException(404, f"Unknown ticker: {sym}")

    df = _comp_d.get(sym)
    if df is None or df.empty:
        raise HTTPException(503, "No data available")

    res = BT.run_backtest(df, entry=entry, exit_th=exit_th,
                          slope_bars=slope_bars, hold_through_neutral=True)
    if not res:
        raise HTTPException(500, "Backtest returned no results")

    def _date(d) -> str:
        return pd.Timestamp(d).strftime("%Y-%m-%d")

    trades_out = [
        {
            "entry_date":  _date(t["entry_date"]),
            "exit_date":   _date(t["exit_date"]),
            "entry_price": float(t["entry_price"]),
            "exit_price":  float(t["exit_price"]),
            "return":      float(t["return"]),
            "open":        bool(t["open"]),
        }
        for t in res["trades"]
    ]

    payload = {
        "stats": {
            "total_return": float(res["total_return"]),
            "bh_return":    float(res["bh_return"]),
            "max_drawdown": float(res["max_drawdown"]),
            "win_rate":     float(res["win_rate"]),
            "sharpe":       float(res["sharpe"]),
            "n_trades":     int(res["n_trades"]),
        },
        "equity": _tv_line(res["equity"]),
        "bh":     _tv_line(res["bh"]),
        "closes": _tv_line(res["closes"]),
        "states": [{"time": _date(dt), "state": state} for dt, state in res["states"].items()],
        "score":  _tv_line(Sig.score_history(df, n=len(df))),
        "trades": trades_out,
    }
    return JSONResponse(payload)


class _AlertCreate(BaseModel):
    symbol:         str
    condition_type: str   # "price_above" | "price_below" | "signal_bull" | "signal_bear"
    threshold:      float | None = None


@app.get("/api/market")
def get_market() -> JSONResponse:
    try:
        batch   = Data.fetch_symbols_batch(["^VIX", "^MOVE"], "1d")
        vix_df  = batch.get("^VIX")
        move_df = batch.get("^MOVE")
        vix  = float(vix_df["Close"].dropna().iloc[-1])  if vix_df  is not None and not vix_df.empty  else None
        move = slope = None
        if move_df is not None and not move_df.empty:
            mc    = move_df["Close"].dropna()
            move  = float(mc.iloc[-1])
            win   = mc.iloc[-10:].values.astype(float)
            slope = float(np.polyfit(np.arange(len(win)), win, 1)[0]) if len(win) >= 2 else None
        return JSONResponse({"vix": vix, "move": move, "move_slope": slope})
    except Exception as exc:
        return JSONResponse({"vix": None, "move": None, "move_slope": None})


@app.get("/api/alerts")
def list_alerts() -> JSONResponse:
    return JSONResponse(db.list_alerts())


@app.post("/api/alerts", status_code=201)
def create_alert(body: _AlertCreate) -> JSONResponse:
    try:
        alert = db.create_alert(body.symbol, body.condition_type, body.threshold)
        return JSONResponse(alert, status_code=201)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))


@app.delete("/api/alerts/{alert_id}", status_code=204)
def delete_alert(alert_id: int) -> None:
    try:
        found = db.delete_alert(alert_id)
        if not found:
            raise HTTPException(404, "Alert not found")
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))


@app.websocket("/ws/status")
async def ws_status(websocket: WebSocket) -> None:
    await _ws.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        _ws.disconnect(websocket)


# ── Serve React build ─────────────────────────────────────────────────────────

_DIST = pathlib.Path(__file__).parent.parent / "frontend" / "dist"
if _DIST.exists():
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="static")
