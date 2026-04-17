# signals.py  –  Extract human-readable signals and bull/bear classifications

import numpy as np
import pandas as pd
from config import (STOCHRSI_CONFIGS, MA_PERIODS, VOLUME_MA_PERIOD, VOLUME_TREND_DAYS,
                    OBV_TREND_DAYS, SIGNAL_ENTRY, SIGNAL_EXIT, SIGNAL_SLOPE_BARS)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _last(df: pd.DataFrame, col: str) -> float:
    if col not in df.columns:
        return np.nan
    s = df[col].dropna()
    return float(s.iloc[-1]) if len(s) else np.nan


def _slope(df: pd.DataFrame, col: str, days: int) -> float:
    if col not in df.columns:
        return 0.0
    s = df[col].dropna().tail(days)
    if len(s) < 2:
        return 0.0
    x = np.arange(len(s), dtype=float)
    return float(np.polyfit(x, s.values.astype(float), 1)[0])


def _up(condition: bool) -> str:
    return "↑" if condition else "↓"


def _fmt(val: float, dec: int = 2) -> str:
    if np.isnan(val):
        return "N/A"
    if abs(val) >= 1_000_000:
        return f"{val/1_000_000:.2f}M"
    if abs(val) >= 1_000:
        return f"{val/1_000:.1f}K"
    return f"{val:.{dec}f}"


def _pct(val: float) -> str:
    if np.isnan(val):
        return "N/A"
    sign = "+" if val >= 0 else ""
    return f"{sign}{val:.1f}%"


# ── Vectorized per-bar score (used for SMA smoothing) ─────────────────────────

def _rolling_slope(series: pd.Series, window: int) -> pd.Series:
    """Rolling linear regression slope to match the _slope() polyfit logic."""
    x = np.arange(window, dtype=float)
    def _s(y):
        try:
            return float(np.polyfit(x, y, 1)[0])
        except Exception:
            return 0.0
    return series.rolling(window).apply(_s, raw=True)


def _score_series(df: pd.DataFrame) -> pd.Series:
    """Return the raw net score for every bar (buy − sell), vectorised."""
    c    = df["Close"].squeeze() if isinstance(df["Close"], pd.DataFrame) else df["Close"]
    buy  = pd.Series(0.0, index=df.index)
    sell = pd.Series(0.0, index=df.index)

    def _col(name):
        return df[name] if name in df.columns else None

    # RSI condition 1: rolling slope over 20 bars on EMA(RSI,14) AND RSI > RSI_MA
    rsi, rsi_ma = _col("RSI"), _col("RSI_MA")
    rsi_ema     = _col("RSI_EMA")
    if rsi is not None and rsi_ma is not None:
        rsi_slope = _rolling_slope(rsi_ema if rsi_ema is not None else rsi, 20)
        rsi_up    = rsi_slope > 0
        rsi_ab    = rsi > rsi_ma
        buy  += np.where(rsi_up  &  rsi_ab,  10, 0)
        sell += np.where(~rsi_up & ~rsi_ab,  10, 0)

    # RSI condition 2: level
    if rsi is not None:
        buy  += np.where(rsi >= 56, 10, 0)
        sell += np.where(rsi <= 36, 10, 0)

    # EMA50 + SMA50
    e50, s50 = _col("EMA_50"), _col("SMA_50")
    if e50 is not None and s50 is not None:
        buy  += np.where((c > e50) & (c > s50), 5, 0)
        sell += np.where((c < e50) & (c < s50), 5, 0)

    # EMA200 + SMA200
    e200, s200 = _col("EMA_200"), _col("SMA_200")
    if e200 is not None and s200 is not None:
        buy  += np.where((c > e200) & (c > s200), 5, 0)
        sell += np.where((c < e200) & (c < s200), 5, 0)

    # Ichimoku cloud
    ca, cb = _col("ICHI_CLOUD_A"), _col("ICHI_CLOUD_B")
    if ca is not None and cb is not None:
        cloud_top = pd.concat([ca, cb], axis=1).max(axis=1)
        cloud_bot = pd.concat([ca, cb], axis=1).min(axis=1)
        buy  += np.where(c > cloud_top, 5, 0)
        sell += np.where(c < cloud_bot, 5, 0)

    # Ichimoku base
    kijun = _col("ICHI_KIJUN")
    if kijun is not None:
        buy  += np.where(c > kijun, 5, 0)
        sell += np.where(c < kijun, 5, 0)

    # OBV: above EMA AND rolling slope up
    obv, obv_ma = _col("OBV"), _col("OBV_MA")
    if obv is not None and obv_ma is not None:
        obv_slope = _rolling_slope(obv, OBV_TREND_DAYS)
        obv_up    = obv_slope > 0
        obv_ab    = obv > obv_ma
        buy  += np.where( obv_ab &  obv_up, 10, 0)
        sell += np.where(~obv_ab & ~obv_up, 10, 0)

    # Keltner: beyond band AND widening
    kc_u, kc_l   = _col("KC_UPPER"), _col("KC_LOWER")
    kc_w, kc_ws  = _col("KC_WIDTH"), _col("KC_WIDTH_SMA")
    if all(x is not None for x in [kc_u, kc_l, kc_w, kc_ws]):
        widening = kc_w > kc_ws * 1.05
        buy  += np.where((c > kc_u) & widening,  10, 0)
        sell += np.where((c < kc_l) & widening,  10, 0)

    # CNV
    cnv_tb = _col("CNV_TB")
    if cnv_tb is not None:
        buy  += np.where(cnv_tb >  0, 10, 0)
        sell += np.where(cnv_tb <= 0, 10, 0)

    return buy - sell


def score_history(df: pd.DataFrame, n: int = 60) -> pd.Series:
    """Return the last n bars of SMA(5)-smoothed net score (mirrors Pine's scoreSmooth)."""
    raw = _score_series(df)
    return raw.rolling(5).mean().dropna().tail(n)


def signal_state_history(df: pd.DataFrame, n: int = 126,
                         entry: int = SIGNAL_ENTRY, exit_th: int = SIGNAL_EXIT,
                         slope_bars: int = SIGNAL_SLOPE_BARS) -> pd.Series:
    """
    Per-bar BULL/BEAR/NEUTRAL state using hysteresis + slope confirmation.
    Entry: score crosses ±entry with slope in the right direction.
    Exit:  score retreats past ±exit_th (inner band).
    """
    raw    = _score_series(df)
    smooth = raw.rolling(5).mean()
    slope5 = _rolling_slope(smooth.fillna(0), slope_bars)

    state  = "NEUTRAL"
    states = []
    for score, slope in zip(smooth, slope5):
        if pd.isna(score):
            states.append("NEUTRAL")
            continue
        if state == "NEUTRAL":
            if score > entry and slope > 0:
                state = "BULL"
            elif score < -entry and slope < 0:
                state = "BEAR"
        elif state == "BULL":
            if score < exit_th:
                state = "NEUTRAL"
        elif state == "BEAR":
            if score > -exit_th:
                state = "NEUTRAL"
        states.append(state)

    return pd.Series(states, index=smooth.index).tail(n)


def get_signal_state(df: pd.DataFrame,
                     entry: int = SIGNAL_ENTRY, exit_th: int = SIGNAL_EXIT) -> dict:
    """Current signal with score value, 5-bar slope, and bars held in state."""
    hist = signal_state_history(df, n=len(df), entry=entry, exit_th=exit_th)
    if len(hist) == 0:
        return {"signal": "NEUTRAL", "score": 0, "slope": 0.0, "bars_held": 0}

    current   = hist.iloc[-1]
    bars_held = int((hist[::-1] == current).cumprod().sum())

    raw       = _score_series(df)
    smooth    = raw.rolling(5).mean().dropna()
    score_val = float(smooth.iloc[-1]) if len(smooth) else 0.0

    slope5 = _rolling_slope(smooth, SIGNAL_SLOPE_BARS).dropna()
    slope  = float(slope5.iloc[-1]) if len(slope5) else 0.0

    return {
        "signal":    current,           # "BULL" | "BEAR" | "NEUTRAL"
        "score":     int(round(score_val)),
        "slope":     round(slope, 2),   # positive = improving, negative = deteriorating
        "bars_held": bars_held,
    }


# ── Score helpers ──────────────────────────────────────────────────────────────

def _score(bulls: list) -> tuple[int, int]:
    # Denominator is always the full indicator count (None counts as not bullish)
    n_bull = sum(1 for b in bulls if b == True)
    return (n_bull, len(bulls))


def _overall(bulls: list):
    n_bull, total = _score(bulls)
    if total == 0:
        return None
    ratio = n_bull / total
    if ratio >= 0.65:
        return True
    if ratio <= 0.35:
        return False
    return None


# ── Main ───────────────────────────────────────────────────────────────────────

def get_signals(df: pd.DataFrame) -> dict:
    closes     = df["Close"].dropna()
    last_close = float(closes.iloc[-1]) if len(closes) else np.nan
    prev_close = float(closes.iloc[-2]) if len(closes) >= 2 else np.nan
    pct_change = (last_close / prev_close - 1) * 100 if not (np.isnan(last_close) or np.isnan(prev_close)) else np.nan
    s: dict = {"close": last_close, "pct_change": pct_change}

    # ── RSI ───────────────────────────────────────────────────────────────────
    rsi_val   = _last(df, "RSI")
    rsi_ma    = _last(df, "RSI_MA")
    # Slope on EMA-smoothed RSI to match Pine Script: rsiSmooth = ta.ema(rsi, 14)
    rsi_slope = _slope(df, "RSI_EMA" if "RSI_EMA" in df.columns else "RSI", 20)

    rsi_up    = rsi_slope > 0
    rsi_above = (rsi_val > rsi_ma) if not (np.isnan(rsi_val) or np.isnan(rsi_ma)) else None
    rsi_zone  = "OB" if rsi_val > 70 else ("OS" if rsi_val < 30 else "")

    # Condition 1 (scoring): slope > 0 AND rsi > SMA(RSI,14)
    if rsi_up and rsi_above == True:        b_rsi1 = True
    elif not rsi_up and rsi_above == False: b_rsi1 = False
    else:                                   b_rsi1 = None

    zone_tag = f" [{rsi_zone}]" if rsi_zone else ""
    s["RSI"] = {
        "value": rsi_val,
        "text":  f"{_fmt(rsi_val,1)}  Trend {_up(rsi_up)}  MA {_up(bool(rsi_above))}{zone_tag}",
        "bull":  b_rsi1,
        "slope": rsi_slope,
    }

    # ── Stochastic RSI ────────────────────────────────────────────────────────
    s["StochRSI"] = {}
    for cfg in STOCHRSI_CONFIGS:
        lbl   = cfg["label"]
        k     = _last(df, f"SRSI_{lbl}_K")
        d     = _last(df, f"SRSI_{lbl}_D")
        k_slp  = _slope(df, f"SRSI_{lbl}_K", 3)
        d_slp  = _slope(df, f"SRSI_{lbl}_D", 3)
        k_up   = k_slp > 0
        d_up   = d_slp > 0
        k_gt_d = (k > d) if not (np.isnan(k) or np.isnan(d)) else None
        zone   = "OB" if k > 80 else ("OS" if k < 20 else "")
        # Green if K above D, red if K below D (always colored when data exists)
        bull   = bool(k_gt_d)      if k_gt_d is not None else False
        bear   = bool(not k_gt_d)  if k_gt_d is not None else False
        zone_tag = f" [{zone}]" if zone else ""
        s["StochRSI"][lbl] = {
            "K": k, "D": d,
            "text": f"K:{_fmt(k,1)}{_up(k_up)}  D:{_fmt(d,1)}{_up(d_up)}{zone_tag}",
            "bull": True if bull else (False if bear else None),
        }

    # ── EMA / SMA ─────────────────────────────────────────────────────────────
    s["EMA"] = {}
    s["SMA"] = {}
    ema_bulls, sma_bulls = [], []
    for p in MA_PERIODS:
        ema_val = _last(df, f"EMA_{p}")
        sma_val = _last(df, f"SMA_{p}")
        ema_ab  = (last_close > ema_val) if not np.isnan(ema_val) else None
        sma_ab  = (last_close > sma_val) if not np.isnan(sma_val) else None
        s["EMA"][p] = {"value": ema_val, "above": ema_ab}
        s["SMA"][p] = {"value": sma_val, "above": sma_ab}
        ema_bulls.append(ema_ab)
        sma_bulls.append(sma_ab)

    def _ma_text(ma_dict):
        parts = [f"{p}:{_up(bool(ma_dict[p]['above']))}" for p in MA_PERIODS]
        return "  ".join(parts)

    def _ma_bull(bulls):
        valid = [b for b in bulls if b is not None]
        if not valid:
            return None
        score = sum(1 for b in valid if b)
        if score == len(valid): return True
        if score == 0:          return False
        return None

    s["EMA"]["text"] = _ma_text(s["EMA"])
    s["SMA"]["text"] = _ma_text(s["SMA"])
    s["EMA"]["bull"] = _ma_bull(ema_bulls)
    s["SMA"]["bull"] = _ma_bull(sma_bulls)

    # ── Bull Market Support Band ───────────────────────────────────────────────
    b_sma = _last(df, "BULL_SMA")
    b_ema = _last(df, "BULL_EMA")
    if not (np.isnan(b_sma) or np.isnan(b_ema)):
        band_hi = max(b_sma, b_ema)
        band_lo = min(b_sma, b_ema)
        if last_close > band_hi:
            pos, b_bb = "Above Band", True
        elif last_close < band_lo:
            pos, b_bb = "Below Band", False
        else:
            pos, b_bb = "Inside Band", None
    else:
        pos, b_bb = "N/A", None

    s["BullBand"] = {"text": pos, "bull": b_bb, "sma": b_sma, "ema": b_ema}

    # ── Ichimoku ──────────────────────────────────────────────────────────────
    kijun   = _last(df, "ICHI_KIJUN")
    cloud_a = _last(df, "ICHI_CLOUD_A")
    cloud_b = _last(df, "ICHI_CLOUD_B")
    if not (np.isnan(kijun) or np.isnan(cloud_a) or np.isnan(cloud_b)):
        above_base = last_close > kijun
        cloud_top  = max(cloud_a, cloud_b)
        cloud_bot  = min(cloud_a, cloud_b)
        if last_close > cloud_top:
            cloud_pos, b_cloud = "Above Cloud", True
        elif last_close < cloud_bot:
            cloud_pos, b_cloud = "Below Cloud", False
        else:
            cloud_pos, b_cloud = "In Cloud", None
        base_text = _up(above_base)
        s["Ichimoku"] = {
            "cloud_text": cloud_pos,
            "base_text":  base_text,
            "cloud_bull": b_cloud,
            "base_bull":  above_base,
        }
    else:
        s["Ichimoku"] = {
            "cloud_text": "N/A", "base_text": "N/A",
            "cloud_bull": None,  "base_bull":  None,
        }

    # ── Volume ────────────────────────────────────────────────────────────────
    vol_series = df["Volume"].dropna() if "Volume" in df.columns else pd.Series(dtype=float)
    vol_ma     = _last(df, "VOL_MA")
    if len(vol_series) >= 3 and not np.isnan(vol_ma):
        v0, v1, v2 = float(vol_series.iloc[-1]), float(vol_series.iloc[-2]), float(vol_series.iloc[-3])
        above_ma   = v0 > vol_ma
        increasing = v0 > v1 > v2
        decreasing = v0 < v1 < v2
        ma_part  = f"MA {_up(above_ma)}"
        if increasing or decreasing:
            vol_text = f"{ma_part}  Trend {_up(increasing)}"
        else:
            vol_text = ma_part
        if above_ma and increasing:
            b_vol = True
        elif not above_ma and decreasing:
            b_vol = False
        else:
            b_vol = None
    else:
        vol_text = "N/A"
        b_vol    = None

    s["Volume"] = {"text": vol_text, "bull": b_vol}

    # ── OBV ───────────────────────────────────────────────────────────────────
    obv_val = _last(df, "OBV")
    obv_ma  = _last(df, "OBV_MA")
    obv_slp = _slope(df, "OBV", OBV_TREND_DAYS)
    obv_up  = obv_slp > 0
    obv_ab  = (obv_val > obv_ma) if not (np.isnan(obv_val) or np.isnan(obv_ma)) else None

    if obv_ab == True and obv_up:    b_obv = True
    elif obv_ab == False and not obv_up: b_obv = False
    else:                            b_obv = None

    s["OBV"] = {
        "text": f"MA {_up(bool(obv_ab))}  Trend {_up(obv_up)}",
        "bull": b_obv,
    }

    # ── Keltner Channel ───────────────────────────────────────────────────────
    kc_b     = _last(df, "KC_BASIS")
    kc_u     = _last(df, "KC_UPPER")
    kc_l     = _last(df, "KC_LOWER")
    kc_w     = _last(df, "KC_WIDTH")
    kc_w_sma = _last(df, "KC_WIDTH_SMA")

    if not np.isnan(kc_b):
        widening = (
            kc_w > kc_w_sma + 0.05 * kc_w_sma
            if not (np.isnan(kc_w) or np.isnan(kc_w_sma))
            else False
        )
        wid_str = "Widening" if widening else "Contracting"
        if last_close > kc_u:
            b_kc    = True if widening else None
            kc_text = f"Above Upper  {wid_str}"
        elif last_close < kc_l:
            b_kc    = False if widening else None
            kc_text = f"Below Lower  {wid_str}"
        elif last_close > kc_b:
            b_kc    = None
            kc_text = f"Above Mid  {wid_str}"
        else:
            b_kc    = None
            kc_text = f"Below Mid  {wid_str}"
        s["Keltner"] = {"text": kc_text, "bull": b_kc}
    else:
        s["Keltner"] = {"text": "N/A", "bull": None}

    # ── CNV ───────────────────────────────────────────────────────────────────
    cnv_tb = _last(df, "CNV_TB")
    if not np.isnan(cnv_tb):
        if cnv_tb > 0:    b_cnv = True
        elif cnv_tb <= 0: b_cnv = False
        s["CNV"] = {
            "text": "Above MA" if b_cnv else "Below MA",
            "bull": b_cnv,
        }
    else:
        s["CNV"] = {"text": "N/A", "bull": None}

    # ── Nadaraya-Watson ───────────────────────────────────────────────────────
    nw_u = _last(df, "NW_UPPER")
    nw_l = _last(df, "NW_LOWER")
    if not (np.isnan(nw_u) or np.isnan(nw_l) or np.isnan(kc_u) or np.isnan(kc_l)):
        # Check if bands are inside the Keltner Channel range
        upper_in = kc_l <= nw_u <= kc_u
        lower_in = kc_l <= nw_l <= kc_u
        nw_mid = _last(df, "NW")

        if upper_in and lower_in:
            nw_text = "Upper/lower in keltner"
        elif upper_in:
            nw_text = "Upper in Keltner"
        elif lower_in:
            nw_text = "Lower in Keltner"
        else:
            nw_text = "Neither in keltner"

        if lower_in and not upper_in:
            nw_bull = True
        elif upper_in and not lower_in:
            nw_bull = False
        else:
            nw_bull = None

        s["NW"] = {
            "text": nw_text,
            "bull": nw_bull,
        }
    else:
        s["NW"] = {"text": "N/A", "bull": None}

    # ── Overall score (weighted, max ±80) ─────────────────────────────────────
    buy_score = sell_score = 0

    def _pts(val: int) -> str:
        return f"+{val}" if val > 0 else (f"-{abs(val)}" if val < 0 else "")

    # RSI condition 1: slope > 0 AND rsi > SMA
    if b_rsi1 == True:   buy_score  += 10
    elif b_rsi1 == False: sell_score += 10
    s["RSI"]["score"] = _pts(10) if b_rsi1 == True else (_pts(-10) if b_rsi1 == False else "")

    # RSI condition 2: level threshold (checked independently)
    rsi_lvl_bull = rsi_val >= 56
    rsi_lvl_bear = rsi_val <= 36
    if rsi_lvl_bull:   buy_score  += 10
    elif rsi_lvl_bear: sell_score += 10
    # Combine both RSI contributions into one score string
    s["RSI"]["score"] = _pts(20) if (b_rsi1 == True and rsi_lvl_bull) else (
        _pts(10) if (b_rsi1 == True or rsi_lvl_bull) else (
        _pts(-20) if (b_rsi1 == False and rsi_lvl_bear) else (
        _pts(-10) if (b_rsi1 == False or rsi_lvl_bear) else "")))

    # EMA+SMA 50 (both required for full points)
    ema50  = _last(df, "EMA_50");  sma50  = _last(df, "SMA_50")
    ema50_bull = ema50_bear = False
    if not (np.isnan(ema50) or np.isnan(sma50)):
        if last_close > ema50 and last_close > sma50:     buy_score  += 5; ema50_bull = True
        elif last_close < ema50 and last_close < sma50:   sell_score += 5; ema50_bear = True
    s["EMA"]["score50"] = _pts(5) if ema50_bull else (_pts(-5) if ema50_bear else "")
    s["SMA"]["score50"] = s["EMA"]["score50"]

    # EMA+SMA 200 (both required for full points)
    ema200 = _last(df, "EMA_200"); sma200 = _last(df, "SMA_200")
    ema200_bull = ema200_bear = False
    if not (np.isnan(ema200) or np.isnan(sma200)):
        if last_close > ema200 and last_close > sma200:   buy_score  += 5; ema200_bull = True
        elif last_close < ema200 and last_close < sma200: sell_score += 5; ema200_bear = True
    s["EMA"]["score200"] = _pts(5) if ema200_bull else (_pts(-5) if ema200_bear else "")
    s["SMA"]["score200"] = s["EMA"]["score200"]

    if s["Ichimoku"]["cloud_bull"]  == True:  buy_score  +=  5
    elif s["Ichimoku"]["cloud_bull"] == False: sell_score +=  5
    s["Ichimoku"]["cloud_score"] = (
        _pts(5) if s["Ichimoku"]["cloud_bull"] == True else
        (_pts(-5) if s["Ichimoku"]["cloud_bull"] == False else ""))

    if s["Ichimoku"]["base_bull"]   == True:  buy_score  +=  5
    elif s["Ichimoku"]["base_bull"]  == False: sell_score +=  5
    s["Ichimoku"]["base_score"] = (
        _pts(5) if s["Ichimoku"]["base_bull"] == True else
        (_pts(-5) if s["Ichimoku"]["base_bull"] == False else ""))

    if s["OBV"]["bull"]             == True:  buy_score  += 10
    elif s["OBV"]["bull"]           == False: sell_score += 10
    s["OBV"]["score"] = (
        _pts(10) if s["OBV"]["bull"] == True else
        (_pts(-10) if s["OBV"]["bull"] == False else ""))

    if s["Keltner"]["bull"]         == True:  buy_score  += 10
    elif s["Keltner"]["bull"]       == False: sell_score += 10
    s["Keltner"]["score"] = (
        _pts(10) if s["Keltner"]["bull"] == True else
        (_pts(-10) if s["Keltner"]["bull"] == False else ""))

    if s["CNV"]["bull"]             == True:  buy_score  += 10
    elif s["CNV"]["bull"]           == False: sell_score += 10
    s["CNV"]["score"] = (
        _pts(10) if s["CNV"]["bull"] == True else
        (_pts(-10) if s["CNV"]["bull"] == False else ""))

    net = buy_score - sell_score

    # SMA(5) smoothing matching Pine Script scoreSmooth = ta.sma(netScore, 5)
    _hist = score_history(df, n=5)
    net_smoothed = int(round(_hist.iloc[-1])) if len(_hist) else net

    sig_state      = get_signal_state(df)
    s["signal"]    = sig_state["signal"]
    s["slope"]     = sig_state["slope"]
    s["bars_held"] = sig_state["bars_held"]
    s["overall"]   = True if sig_state["signal"] == "BULL" else (False if sig_state["signal"] == "BEAR" else None)
    s["score_str"] = f"+{net_smoothed}" if net_smoothed > 0 else str(net_smoothed)

    # Sparkline: 60 bars of smoothed score for Summary cards
    try:
        _spark = score_history(df, n=60)
        s["sparkline"] = [round(float(v), 1) for v in _spark.tolist() if not np.isnan(float(v))]
    except Exception:
        s["sparkline"] = []

    # Signal segments: current and previous contiguous state blocks
    try:
        _hist  = signal_state_history(df, n=len(df))
        _segs: list = []
        if len(_hist) >= 1:
            _st = _hist.iloc[0]
            _si = _hist.index[0]
            for _k in range(1, len(_hist)):
                if _hist.iloc[_k] != _st:
                    _cnt = int(((_hist.index >= _si) & (_hist.index <= _hist.index[_k - 1])).sum())
                    _segs.append({
                        "state": _st,
                        "start": _si.strftime("%b %-d"),
                        "end":   _hist.index[_k - 1].strftime("%b %-d"),
                        "bars":  _cnt,
                    })
                    _st = _hist.iloc[_k]
                    _si = _hist.index[_k]
            _cnt = int(((_hist.index >= _si) & (_hist.index <= _hist.index[-1])).sum())
            _segs.append({
                "state": _st,
                "start": _si.strftime("%b %-d"),
                "end":   "today",
                "bars":  _cnt,
            })
        s["signal_segments"] = _segs[-2:] if len(_segs) >= 2 else _segs
    except Exception:
        s["signal_segments"] = []

    return s
