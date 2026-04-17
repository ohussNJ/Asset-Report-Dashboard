# indicators.py  –  All indicator calculations on a price DataFrame

import numpy as np
import pandas as pd
import pandas_ta as ta
from config import (
    RSI_PERIOD, RSI_MA_PERIOD,
    STOCHRSI_CONFIGS,
    MA_PERIODS,
    BULL_SMA_PERIOD, BULL_EMA_PERIOD,
    VOLUME_MA_PERIOD,
    OBV_MA_PERIOD,
    KC_LENGTH, KC_ATR_LENGTH, KC_SCALAR, KC_WIDTH_SMOOTHING,
    NW_BANDWIDTH, NW_MULTIPLIER, NW_LOOKBACK,
)


# ── Column accessors ───────────────────────────────────────────────────────────

def _c(df):  # close
    col = df["Close"]
    return col.squeeze() if isinstance(col, pd.DataFrame) else col

def _h(df):  # high
    col = df["High"]
    return col.squeeze() if isinstance(col, pd.DataFrame) else col

def _l(df):  # low
    col = df["Low"]
    return col.squeeze() if isinstance(col, pd.DataFrame) else col

def _v(df):  # volume
    col = df["Volume"]
    return col.squeeze() if isinstance(col, pd.DataFrame) else col


# ── Individual indicators ──────────────────────────────────────────────────────

def add_rsi(df: pd.DataFrame) -> pd.DataFrame:
    c = _c(df)
    rsi = ta.rsi(c, length=RSI_PERIOD)
    df = df.copy()
    df["RSI"] = rsi.values
    df["RSI_MA"] = ta.sma(pd.Series(rsi.values, index=df.index),
                          length=RSI_MA_PERIOD).values
    # EMA-smoothed RSI used for slope calculation (matches Pine Script)
    df["RSI_EMA"] = ta.ema(pd.Series(rsi.values, index=df.index),
                           length=RSI_MA_PERIOD).values
    return df


def add_stochrsi(df: pd.DataFrame) -> pd.DataFrame:
    c = _c(df)
    df = df.copy()
    for cfg in STOCHRSI_CONFIGS:
        lbl = cfg["label"]
        try:
            srsi = ta.stochrsi(
                c,
                length=cfg["length"],
                rsi_length=cfg["rsi_length"],
                k=cfg["k"],
                d=cfg["d"],
            )
            if srsi is not None and srsi.shape[1] >= 2:
                df[f"SRSI_{lbl}_K"] = srsi.iloc[:, 0].values
                df[f"SRSI_{lbl}_D"] = srsi.iloc[:, 1].values
        except Exception as exc:
            print(f"[indicators] stochrsi {lbl}: {exc}")
    return df


def add_ema_sma(df: pd.DataFrame) -> pd.DataFrame:
    c = _c(df)
    df = df.copy()
    for p in MA_PERIODS:
        ema = ta.ema(c, length=p)
        sma = ta.sma(c, length=p)
        df[f"EMA_{p}"] = ema.values if ema is not None else np.nan
        df[f"SMA_{p}"] = sma.values if sma is not None else np.nan
    return df


def add_bull_band(df: pd.DataFrame, df_weekly: pd.DataFrame) -> pd.DataFrame:
    """
    Compute 20-week SMA + 21-week EMA from weekly data and align to df's index
    (works for both daily and weekly df).
    """
    df = df.copy()
    if df_weekly.empty:
        df["BULL_SMA"] = np.nan
        df["BULL_EMA"] = np.nan
        return df

    c_w = _c(df_weekly)
    sma_w = ta.sma(c_w, length=BULL_SMA_PERIOD)
    ema_w = ta.ema(c_w, length=BULL_EMA_PERIOD)

    idx_w = df_weekly.index.normalize()
    sma_s = pd.Series(sma_w.values, index=idx_w)
    ema_s = pd.Series(ema_w.values, index=idx_w)

    idx_d = df.index.normalize()
    combined = idx_d.union(idx_w).sort_values()

    sma_aligned = sma_s.reindex(combined).ffill().reindex(idx_d)
    ema_aligned = ema_s.reindex(combined).ffill().reindex(idx_d)

    df["BULL_SMA"] = sma_aligned.values
    df["BULL_EMA"] = ema_aligned.values
    return df


def add_keltner(df: pd.DataFrame) -> pd.DataFrame:
    """
    Keltner Channel matching TradingView defaults:
      Basis = EMA(close, 20)
      Band  = ATR(10)
      Upper = Basis + 2 * ATR
      Lower = Basis - 2 * ATR
    pandas-ta's ta.kc() uses EMA(TR, length) for the band instead of ATR,
    which differs from TradingView, so we build it manually here.
    """
    df = df.copy()
    try:
        basis = ta.ema(_c(df), length=KC_LENGTH)
        atr   = ta.atr(_h(df), _l(df), _c(df), length=KC_ATR_LENGTH)
        upper  = basis + KC_SCALAR * atr
        lower  = basis - KC_SCALAR * atr
        width  = upper - lower
        df["KC_BASIS"]     = basis.values
        df["KC_UPPER"]     = upper.values
        df["KC_LOWER"]     = lower.values
        df["KC_WIDTH"]     = width.values
        df["KC_WIDTH_SMA"] = ta.sma(
            pd.Series(width.values, index=df.index), length=KC_WIDTH_SMOOTHING
        ).values
    except Exception as exc:
        print(f"[indicators] keltner: {exc}")
        df["KC_LOWER"] = df["KC_BASIS"] = df["KC_UPPER"] = np.nan
    return df


def add_nadaraya_watson(df: pd.DataFrame) -> pd.DataFrame:
    """
    Nadaraya-Watson Envelope matching LuxAlgo Pine Script (repainting mode).

    For each of the last `size` bars, NW is a kernel regression whose center
    shifts to that bar's position (not always anchored at bar 0).
    SAE (band half-width) = simple unweighted average of all residuals × mult
    which captures full historical volatility across the window.

    Pine Script reference:
        gauss(x, h) = exp(-(x^2) / (h*h*2))
        nwe[i] = Σ_j src[j]*gauss(i-j,h) / Σ_j gauss(i-j,h)  for j=0..size
        sae     = Σ_i |src[i] - nwe[i]| / size * mult
        bands   = nwe[i] ± sae
    """
    close = _c(df).values.astype(float)
    n     = len(close)

    df = df.copy()
    df["NW"]       = np.nan
    df["NW_UPPER"] = np.nan
    df["NW_LOWER"] = np.nan

    if n < 2:
        return df

    h    = NW_BANDWIDTH
    size = min(NW_LOOKBACK - 1, n - 1)   # Pine: math.min(499, n-1)
    lb   = size + 1                        # total bars in window

    # src[j] = close j bars ago from most recent (src[0]=latest, src[size]=oldest)
    src = close[n - lb : n][::-1].copy()

    # Kernel matrix K[i,j] = gauss(i-j, h): each row i centered at bar i
    idx = np.arange(lb, dtype=float)
    K   = np.exp(-((idx[:, None] - idx[None, :]) ** 2) / (2.0 * h * h))

    # NW regression for each bar position
    nwe = (K @ src) / K.sum(axis=1)

    # SAE: simple average of absolute residuals (Pine divides by `size`, not lb)
    sae = np.sum(np.abs(src - nwe)) / size * NW_MULTIPLIER

    # Place values back in chronological order (oldest → newest)
    nw_chrono = nwe[::-1]
    start = n - lb

    nw_arr    = np.full(n, np.nan)
    upper_arr = np.full(n, np.nan)
    lower_arr = np.full(n, np.nan)
    nw_arr[start:n]    = nw_chrono
    upper_arr[start:n] = nw_chrono + sae
    lower_arr[start:n] = nw_chrono - sae

    df["NW"]       = nw_arr
    df["NW_UPPER"] = upper_arr
    df["NW_LOWER"] = lower_arr
    return df


def add_ichimoku(df: pd.DataFrame) -> pd.DataFrame:
    """
    Manual Ichimoku calculation (avoids pandas-ta column naming inconsistencies).
    Cloud values are shifted 26 bars forward so they align with the current bar.
    """
    df   = df.copy()
    high = _h(df)
    low  = _l(df)

    tenkan = (high.rolling(9).max()  + low.rolling(9).min())  / 2   # conversion
    kijun  = (high.rolling(26).max() + low.rolling(26).min()) / 2   # base line

    span_a_raw = (tenkan + kijun) / 2
    span_b_raw = (high.rolling(52).max() + low.rolling(52).min()) / 2

    # Cloud displayed at current bar = spans calculated 26 bars ago → shift forward 26
    df["ICHI_TENKAN"]  = tenkan.values
    df["ICHI_KIJUN"]   = kijun.values
    df["ICHI_CLOUD_A"] = span_a_raw.shift(26).values
    df["ICHI_CLOUD_B"] = span_b_raw.shift(26).values
    return df


def add_volume(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    vol_ma = ta.sma(_v(df), length=VOLUME_MA_PERIOD)
    df["VOL_MA"] = vol_ma.values if vol_ma is not None else np.nan
    return df


def add_cnv(df: pd.DataFrame) -> pd.DataFrame:
    """Cumulative Net Volume: up-day volume positive, down-day negative."""
    df   = df.copy()
    c    = _c(df)
    v    = _v(df)
    chg  = c.diff()
    nv   = pd.Series(
        np.where(chg > 0, v, np.where(chg < 0, -v, 0)),
        index=df.index,
    )
    cnv        = nv.cumsum()
    cnv_ma     = ta.sma(cnv, length=20)
    df["CNV"]    = cnv.values
    df["CNV_MA"] = cnv_ma.values
    df["CNV_TB"] = (cnv - cnv_ma).values   # TB = "above/below" spread
    return df


def add_obv(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    obv = ta.obv(_c(df), _v(df))
    df["OBV"] = obv.values
    df["OBV_MA"] = ta.ema(
        pd.Series(obv.values, index=df.index), length=OBV_MA_PERIOD
    ).values
    return df


# ── Master compute ─────────────────────────────────────────────────────────────

def compute_all(df: pd.DataFrame, df_weekly: pd.DataFrame) -> pd.DataFrame:
    """
    Compute all indicators on `df` (daily or weekly bars).
    Bull Market Support Band always uses `df_weekly` as its source.
    """
    df = add_rsi(df)
    df = add_stochrsi(df)
    df = add_ema_sma(df)
    df = add_bull_band(df, df_weekly)
    df = add_ichimoku(df)
    df = add_keltner(df)
    df = add_nadaraya_watson(df)
    df = add_volume(df)
    df = add_obv(df)
    df = add_cnv(df)
    return df
