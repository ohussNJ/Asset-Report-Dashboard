# charts.py  –  Matplotlib figure generation for per-ticker tabs

import numpy as np
import pandas as pd
import matplotlib.dates as mdates
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter
from config import C, MA_PERIODS, STOCHRSI_CONFIGS
import signals as Sig
import divergence as Div

CHART_BG  = "#1e1e1e"
PANEL_BG  = "#2b2b2b"
GRID_COL  = "#3a3a3a"
TEXT_COL  = "#d0d0d0"
SUB_COL   = "#888888"
SPINE_COL = "#444444"


def _tail(df, n_bars):
    return df.tail(n_bars)

def _style_ax(ax):
    ax.set_facecolor(PANEL_BG)
    ax.tick_params(colors=SUB_COL, labelsize=8, length=3)
    for spine in ax.spines.values():
        spine.set_color(SPINE_COL)
    ax.grid(True, color=GRID_COL, alpha=0.6, linewidth=0.5, linestyle="--")

def _legend(ax, ncol=1):
    ax.legend(fontsize=7, loc="upper left", ncol=ncol,
              facecolor=CHART_BG, edgecolor=SPINE_COL,
              labelcolor=TEXT_COL, framealpha=0.9, handlelength=1.5)

def _vol_fmt(x, _):
    if x >= 1e9: return f"{x/1e9:.1f}B"
    if x >= 1e6: return f"{x/1e6:.1f}M"
    if x >= 1e3: return f"{x/1e3:.0f}K"
    return str(int(x))

def _xaxis(ax, interval):
    if interval == "1d":
        ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    else:
        ax.xaxis.set_major_locator(mdates.MonthLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
    ax.tick_params(axis="x", labelrotation=30, labelsize=8, colors=SUB_COL)


# ── Shared helpers ─────────────────────────────────────────────────────────────

def _draw_candles(ax, df, dates, close):
    """Draw OHLC candlesticks on ax. Falls back to a close line if OHLC missing."""
    if "Open" in df.columns and "High" in df.columns and "Low" in df.columns:
        opens = df["Open"].values
        highs = df["High"].values
        lows  = df["Low"].values
        bar_w = float(np.median(np.diff(mdates.date2num(dates.to_pydatetime())))) * 0.7 \
                if len(dates) > 1 else 0.6
        for mask, col in [(close >= opens, "#4ade80"), (close < opens, "#f87171")]:
            d = dates[mask]
            if not len(d):
                continue
            o, h, l, c = opens[mask], highs[mask], lows[mask], close[mask]
            ax.vlines(d, l, h, color=col, linewidth=0.8, alpha=0.8, zorder=9)
            body_bot = np.minimum(o, c)
            body_h   = np.abs(c - o)
            body_h   = np.where(body_h < 0.0001 * np.abs(c), 0.0001 * np.abs(c), body_h)
            ax.bar(d, body_h, bottom=body_bot, width=bar_w,
                   color=col, alpha=0.85, zorder=10, linewidth=0)
    else:
        ax.plot(dates, close, color="#e0e0e0", lw=1.5, label="Close", zorder=10)


def _draw_price_panel(ax, df, dates, close, ticker=None, interval=None):
    """Candlestick chart + MA overlays + Bull Band. Pass ticker+interval for title."""
    if ticker and interval:
        ax.set_title(
            f"{ticker}   {dates[-1].strftime('%Y-%m-%d')}   {interval.upper()}",
            color=TEXT_COL, fontsize=10, pad=3, loc="left", fontfamily="Segoe UI",
        )
    _draw_candles(ax, df, dates, close)

    # ── Overlays ────────────────────────────────────────────────────────────────
    if "BULL_SMA" in df.columns:
        ax.fill_between(dates, df["BULL_SMA"], df["BULL_EMA"],
                        color=C["bull_sma"], alpha=0.15, label="Bull Band")
        ax.plot(dates, df["BULL_SMA"], color=C["bull_sma"], lw=1.0, alpha=0.7,
                linestyle="-.", label="20w SMA")
        ax.plot(dates, df["BULL_EMA"], color=C["bull_ema"], lw=1.0, alpha=0.7,
                linestyle="-.", label="21w EMA")
    ema_c = [C["ema50"], C["ema100"], C["ema200"]]
    sma_c = [C["sma50"], C["sma100"], C["sma200"]]
    for i, p in enumerate(MA_PERIODS):
        if f"EMA_{p}" in df.columns:
            ax.plot(dates, df[f"EMA_{p}"], color=ema_c[i], lw=1.0, alpha=0.9,
                    label=f"EMA{p}")
        if f"SMA_{p}" in df.columns:
            ax.plot(dates, df[f"SMA_{p}"], color=sma_c[i], lw=1.0, alpha=0.85,
                    linestyle="--", label=f"SMA{p}")
    ax.set_ylabel("Price", color=SUB_COL, fontsize=8)
    handles, labels = ax.get_legend_handles_labels()
    ax.legend(handles, labels, fontsize=7, loc="upper left",
              facecolor=CHART_BG, edgecolor=SPINE_COL, labelcolor=TEXT_COL,
              ncol=5, framealpha=0.9, handlelength=1.5)


def _draw_divergences(ax_price, ax_ind, dates, price, indicator,
                      min_price_pct=0.3, min_ind_delta=3.0):
    """Draw regular divergence lines on price + indicator panels."""
    divs = Div.find_regular_divergences(
        price, indicator, left=5, right=5,
        min_price_pct=min_price_pct, min_ind_delta=min_ind_delta,
    )
    for d in divs:
        col  = C["bull_fg"] if d["type"] == "bullish" else C["bear_fg"]
        pd1, pd2 = dates[d["pi1"]], dates[d["pi2"]]
        id1, id2 = dates[d["ii1"]], dates[d["ii2"]]
        ax_price.plot([pd1, pd2], [d["p1"], d["p2"]],
                      color=col, lw=1.2, linestyle="--", alpha=0.75, zorder=5)
        ax_price.scatter([pd1, pd2], [d["p1"], d["p2"]],
                         color=col, s=22, zorder=6, linewidths=0)
        ax_ind.plot([id1, id2], [d["ind1"], d["ind2"]],
                    color=col, lw=1.2, linestyle="--", alpha=0.75, zorder=5)
        ax_ind.scatter([id1, id2], [d["ind1"], d["ind2"]],
                       color=col, s=22, zorder=6, linewidths=0)


def _make_fig(n_panels, height_ratios, hspace=0.06):
    fig = Figure(figsize=(13, 9), facecolor=CHART_BG, dpi=96)
    gs  = fig.add_gridspec(n_panels, 1, height_ratios=height_ratios,
                           hspace=hspace, left=0.07, right=0.98,
                           top=0.98, bottom=0.08)
    axes = [fig.add_subplot(gs[i]) for i in range(n_panels)]
    for ax in axes:
        _style_ax(ax)
    for ax in axes[:-1]:
        ax.tick_params(labelbottom=False)
    for ax in axes[1:]:
        ax.sharex(axes[0])
    return fig, axes


# ── Volume ─────────────────────────────────────────────────────────────────────

def make_volume_figure(ticker: str, df: pd.DataFrame, interval: str = "1d", n_bars: int = 126) -> Figure:
    df    = _tail(df, n_bars)
    dates = df.index
    close = df["Close"].values

    fig, (ax0, ax1) = _make_fig(2, [5, 2])
    _draw_price_panel(ax0, df, dates, close, ticker, interval)

    diff = np.diff(close, prepend=close[0])
    vcol = [C["vol_up"] if d >= 0 else C["vol_down"] for d in diff]
    ax1.bar(dates, df["Volume"].values, color=vcol, alpha=0.7, width=0.8)
    if "VOL_MA" in df.columns:
        ax1.plot(dates, df["VOL_MA"], color=C["vol_ma"], lw=1.0, label="Vol MA")
        _legend(ax1)
    ax1.yaxis.set_major_formatter(FuncFormatter(_vol_fmt))
    ax1.set_ylabel("Volume", color=SUB_COL, fontsize=8)
    _xaxis(ax1, interval)
    return fig


# ── Score ──────────────────────────────────────────────────────────────────────

def make_score_figure(ticker: str, df: pd.DataFrame, interval: str = "1d", n_bars: int = 126) -> Figure:
    score_series = Sig.score_history(df, n=len(df))
    state_hist   = Sig.signal_state_history(df, n=len(df))
    df    = _tail(df, n_bars)
    dates = df.index
    close = df["Close"].values
    score_series = score_series.reindex(df.index)
    state_hist   = state_hist.reindex(df.index).fillna("NEUTRAL")

    fig, (ax0, ax1) = _make_fig(2, [5, 2])
    _draw_price_panel(ax0, df, dates, close, ticker, interval)

    sc_vals    = score_series.values
    sc_dates   = score_series.index
    bull_mask  = (state_hist == "BULL").values
    bear_mask  = (state_hist == "BEAR").values
    last_state = state_hist.iloc[-1] if len(state_hist) else "NEUTRAL"
    sc_color   = C["bull_fg"] if last_state == "BULL" else C["bear_fg"] if last_state == "BEAR" else C["neut_fg"]

    ax1.axhline(0,   color="#555555", lw=0.8, linestyle=":",  alpha=0.8)
    ax1.axhline( 30, color="#3a5a3a", lw=0.7, linestyle="--", alpha=0.6)
    ax1.axhline(-30, color="#5a3a3a", lw=0.7, linestyle="--", alpha=0.6)
    ax1.axhline( 70, color=C["bear_fg"], lw=0.7, linestyle="--", alpha=0.5)
    ax1.axhline(-70, color=C["bull_fg"], lw=0.7, linestyle="--", alpha=0.5)
    ax1.fill_between(sc_dates, -10, 10, color="#333333", alpha=0.25)
    ax1.fill_between(sc_dates, 0, sc_vals, where=bull_mask, color=C["bull_fg"], alpha=0.20, interpolate=True)
    ax1.fill_between(sc_dates, 0, sc_vals, where=bear_mask, color=C["bear_fg"], alpha=0.20, interpolate=True)
    ax1.plot(sc_dates, sc_vals, color=sc_color, lw=1.2)
    ax1.set_ylim(-70, 70)
    ax1.set_yticks([-70, -30, -10, 0, 10, 30, 70])
    ax1.set_ylabel("Score", color=SUB_COL, fontsize=8)
    _xaxis(ax1, interval)

    # Annotate current score value at the right edge
    last_sc = sc_vals[-1] if len(sc_vals) and not (sc_vals[-1] != sc_vals[-1]) else None
    if last_sc is not None:
        sc_sign = "+" if last_sc >= 0 else ""
        ax1.axhline(last_sc, color=sc_color, lw=0.6, linestyle=":", alpha=0.5)
        ax1.annotate(
            f"{sc_sign}{int(round(last_sc))}",
            xy=(1, last_sc), xycoords=("axes fraction", "data"),
            xytext=(4, 0), textcoords="offset points",
            color=sc_color, fontsize=8, va="center", fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.2", fc="#1e1e1e", ec=sc_color, lw=0.8, alpha=0.9),
        )

    sc_arr = sc_vals.astype(float) if sc_vals.dtype.kind != 'f' else sc_vals
    _draw_divergences(ax0, ax1, dates, close, sc_arr, min_price_pct=0.3, min_ind_delta=3.0)
    return fig


# ── RSI ────────────────────────────────────────────────────────────────────────

def make_rsi_figure(ticker: str, df: pd.DataFrame, interval: str = "1d", n_bars: int = 126) -> Figure:
    df    = _tail(df, n_bars)
    dates = df.index
    close = df["Close"].values

    fig, (ax0, ax1) = _make_fig(2, [5, 2])
    _draw_price_panel(ax0, df, dates, close, ticker, interval)

    if "RSI" in df.columns:
        rsi = df["RSI"].values
        ax1.plot(dates, rsi, color=C["rsi"], lw=1.1, label="RSI")
        if "RSI_MA" in df.columns:
            ax1.plot(dates, df["RSI_MA"], color=C["rsi_ma"], lw=0.8,
                     linestyle="--", label="RSI MA")
        ax1.axhline(70, color=C["bear_fg"], lw=0.7, linestyle="--", alpha=0.7)
        ax1.axhline(50, color=SUB_COL,     lw=0.5, linestyle=":",  alpha=0.5)
        ax1.axhline(30, color=C["bull_fg"], lw=0.7, linestyle="--", alpha=0.7)
        ax1.fill_between(dates, 70, rsi, where=rsi >= 70, color=C["bear_fg"], alpha=0.12)
        ax1.fill_between(dates, rsi, 30,  where=rsi <= 30, color=C["bull_fg"], alpha=0.12)
        ax1.set_ylim(0, 100)
        ax1.set_yticks([30, 50, 70])
        _legend(ax1, ncol=2)
        _draw_divergences(ax0, ax1, dates, close, rsi, min_price_pct=0.3, min_ind_delta=2.0)
    ax1.set_ylabel("RSI", color=SUB_COL, fontsize=8)
    _xaxis(ax1, interval)
    return fig


# ── StochRSI ───────────────────────────────────────────────────────────────────

def make_stoch_figure(ticker: str, df: pd.DataFrame, interval: str = "1d", n_bars: int = 126) -> Figure:
    df    = _tail(df, n_bars)
    dates = df.index
    close = df["Close"].values

    fig, axes = _make_fig(3, [5, 2, 2])
    ax0 = axes[0]
    _draw_price_panel(ax0, df, dates, close, ticker, interval)

    for i, cfg in enumerate(STOCHRSI_CONFIGS):
        ax  = axes[1 + i]
        lbl = cfg["label"]
        kc, dc = f"SRSI_{lbl}_K", f"SRSI_{lbl}_D"
        if kc in df.columns:
            k = df[kc].values
            d = df[dc].values
            ax.plot(dates, k, color=C["k_line"], lw=1.1, label="K")
            ax.plot(dates, d, color=C["d_line"], lw=0.8, linestyle="--", label="D")
            ax.axhline(80, color=C["bear_fg"], lw=0.7, linestyle="--", alpha=0.7)
            ax.axhline(20, color=C["bull_fg"], lw=0.7, linestyle="--", alpha=0.7)
            ax.fill_between(dates, 80, k, where=k >= 80, color=C["bear_fg"], alpha=0.10)
            ax.fill_between(dates, k, 20,  where=k <= 20, color=C["bull_fg"], alpha=0.10)
            ax.fill_between(dates, k, d, where=k >= d, color=C["bull_fg"], alpha=0.07)
            ax.fill_between(dates, k, d, where=k <  d, color=C["bear_fg"], alpha=0.07)
            ax.set_ylim(0, 100)
            ax.set_yticks([20, 50, 80])
            _legend(ax, ncol=2)
        label = "Slow StochRSI" if i == 0 else "Fast StochRSI"
        ax.set_ylabel(label, color=SUB_COL, fontsize=7)

    _xaxis(axes[-1], interval)
    return fig


# ── OBV ────────────────────────────────────────────────────────────────────────

def make_obv_figure(ticker: str, df: pd.DataFrame, interval: str = "1d", n_bars: int = 126) -> Figure:
    df    = _tail(df, n_bars)
    dates = df.index
    close = df["Close"].values

    fig, (ax0, ax1) = _make_fig(2, [5, 2])
    _draw_price_panel(ax0, df, dates, close, ticker, interval)

    if "OBV" in df.columns:
        obv    = df["OBV"].values
        obv_ma = df["OBV_MA"].values if "OBV_MA" in df.columns else None
        ax1.plot(dates, obv, color=C["obv"], lw=1.1, label="OBV")
        if obv_ma is not None:
            ax1.plot(dates, obv_ma, color=C["obv_ma"], lw=0.8,
                     linestyle="--", label="OBV MA")
            ax1.fill_between(dates, obv, obv_ma, where=obv >= obv_ma,
                             color=C["bull_fg"], alpha=0.10)
            ax1.fill_between(dates, obv, obv_ma, where=obv < obv_ma,
                             color=C["bear_fg"], alpha=0.10)
        _legend(ax1, ncol=2)
        # OBV divergence: min delta scaled to 1% of visible range
        obv_range    = np.nanmax(obv) - np.nanmin(obv)
        obv_min_delta = max(obv_range * 0.01, 1.0)
        _draw_divergences(ax0, ax1, dates, close, obv,
                          min_price_pct=0.3, min_ind_delta=obv_min_delta)
    ax1.yaxis.set_major_formatter(FuncFormatter(_vol_fmt))
    ax1.set_ylabel("OBV", color=SUB_COL, fontsize=8)
    _xaxis(ax1, interval)
    return fig


# ── Keltner + CNV ──────────────────────────────────────────────────────────────

def make_kc_cnv_figure(ticker: str, df: pd.DataFrame, interval: str = "1d", n_bars: int = 126) -> Figure:
    # Grab lookback prices from the full df BEFORE tailing so the reference
    # lines always reflect 17/42 bars back from today regardless of zoom level.
    close_full = df["Close"].dropna()
    price_17 = float(close_full.iloc[-17]) if len(close_full) >= 17 else None
    price_42 = float(close_full.iloc[-42]) if len(close_full) >= 42 else None

    def _price_lbl(p):
        if p is None:
            return ""
        if p >= 1_000:
            return f"${p/1_000:.2f}k"
        if p >= 1:
            return f"${p:.2f}"
        return f"${p:.4f}"

    df    = _tail(df, n_bars)
    dates = df.index
    close = df["Close"].values

    fig, (ax0, ax1) = _make_fig(2, [5, 2])

    # ── Price panel: candlestick + Keltner only (no MAs) ───────────────────────
    ax0.set_title(
        f"{ticker}   {dates[-1].strftime('%Y-%m-%d')}   {interval.upper()}",
        color=TEXT_COL, fontsize=10, pad=3, loc="left", fontfamily="Segoe UI",
    )

    _draw_candles(ax0, df, dates, close)

    if "KC_UPPER" in df.columns:
        ax0.plot(dates, df["KC_UPPER"], color=C["kc"], lw=1.0, alpha=0.85, label="KC Upper")
        ax0.plot(dates, df["KC_LOWER"], color=C["kc"], lw=1.0, alpha=0.85, label="KC Lower")
        ax0.plot(dates, df["KC_BASIS"], color=C["kc"], lw=0.7, alpha=0.5,
                 linestyle="--", label="KC Basis")
        ax0.fill_between(dates, df["KC_LOWER"], df["KC_UPPER"],
                         color=C["kc"], alpha=0.06)

    if "NW_UPPER" in df.columns:
        ax0.plot(dates, df["NW_UPPER"], color="#4ade80", lw=1.0, alpha=0.85,
                 linestyle=":", label="NW Upper")
        ax0.plot(dates, df["NW_LOWER"], color="#f87171", lw=1.0, alpha=0.85,
                 linestyle=":", label="NW Lower")

    if price_17 is not None:
        ax0.axhline(price_17, color="#a855f7", lw=1.0, linestyle="--", alpha=0.85,
                    label=f"17-bar  {_price_lbl(price_17)}")
    if price_42 is not None:
        ax0.axhline(price_42, color="#60a5fa", lw=1.0, linestyle="--", alpha=0.85,
                    label=f"42-bar  {_price_lbl(price_42)}")

    ax0.set_ylabel("Price", color=SUB_COL, fontsize=8)
    handles, labels = ax0.get_legend_handles_labels()
    ax0.legend(handles, labels, fontsize=7, loc="upper left",
               facecolor=CHART_BG, edgecolor=SPINE_COL, labelcolor=TEXT_COL,
               ncol=4, framealpha=0.9, handlelength=1.5)

    # ── CNV_TB panel: histogram matching Pine Script style ─────────────────────
    # Pine: cnv_tb = cum(nv) - sma(cum(nv), 20)
    # Plotted as columns: blue >= 0, red < 0
    # Background zone: faint blue (bull state) / red (bear state)
    # B marker on crossover above 0, S marker on crossunder below 0
    if "CNV_TB" in df.columns:
        tb = df["CNV_TB"].values

        # Bar width matches price panel
        if len(dates) > 1:
            cnv_bar_w = float(np.median(np.diff(mdates.date2num(dates.to_pydatetime())))) * 0.85
        else:
            cnv_bar_w = 0.6

        bull_mask = tb >= 0
        bear_mask = ~bull_mask

        # Background zone (transp=90 equivalent → very faint)
        ax1.fill_between(dates, -1e18, 1e18, where=bull_mask,
                         color="#3b82f6", alpha=0.07, zorder=0, interpolate=True)
        ax1.fill_between(dates, -1e18, 1e18, where=bear_mask,
                         color="#ef4444", alpha=0.07, zorder=0, interpolate=True)

        # Histogram columns
        ax1.bar(dates[bull_mask], tb[bull_mask], width=cnv_bar_w,
                color="#3b82f6", alpha=0.85, linewidth=0, zorder=2)
        ax1.bar(dates[bear_mask], tb[bear_mask], width=cnv_bar_w,
                color="#ef4444", alpha=0.85, linewidth=0, zorder=2)

        # Zero line
        ax1.axhline(0, color="#666666", lw=0.8, linestyle="-", alpha=0.6, zorder=3)

        # B / S crossover markers
        for i in range(1, len(tb)):
            if not (np.isnan(tb[i]) or np.isnan(tb[i - 1])):
                if tb[i - 1] <= 0 and tb[i] > 0:   # crossover → B
                    ax1.annotate("B", xy=(dates[i], tb.min()),
                                 fontsize=6, color="#4ade80", fontweight="bold",
                                 ha="center", va="top", zorder=5)
                elif tb[i - 1] >= 0 and tb[i] < 0:  # crossunder → S
                    ax1.annotate("S", xy=(dates[i], tb.max()),
                                 fontsize=6, color="#f87171", fontweight="bold",
                                 ha="center", va="bottom", zorder=5)

        ax1.yaxis.set_major_formatter(FuncFormatter(_vol_fmt))
        ax1.set_ylabel("CNV", color=SUB_COL, fontsize=8)
        # Clamp y-axis so the fill_between extremes don't blow the scale
        pad = max(abs(np.nanmax(tb)), abs(np.nanmin(tb))) * 0.15
        ax1.set_ylim(np.nanmin(tb) - pad, np.nanmax(tb) + pad)

    _xaxis(ax1, interval)
    return fig
