# report.py – Multi-timeframe signal report: data + HTML generation

import numpy as np
import pandas as pd
from datetime import datetime

import data as Data
import indicators
import signals as Sig
from divergence import find_regular_divergences
from config import TICKERS, WATCHLIST, DIVERGENCE_PARAMS

INTERVALS   = ["3h", "1d", "3d", "1wk"]
_IV_LABEL   = {"3h": "3H", "1d": "1D", "3d": "3D", "1wk": "1W"}

# Helpers

def _arrow(slope: float) -> str:
    if slope >  0.3: return "↑"
    if slope < -0.3: return "↓"
    return "→"


def _pct(val) -> str:
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "—"
    sign = "+" if val >= 0 else ""
    return f"{sign}{val:.1f}%"


def _price_str(val) -> str:
    if val is None:
        return "—"
    if val >= 1_000:
        return f"{val:,.0f}"
    if val >= 10:
        return f"{val:.2f}"
    return f"{val:.4f}"


# Per-ticker data extraction

def _signal_row(comp: pd.DataFrame) -> dict | None:
    if comp is None or comp.empty:
        return None
    try:
        state     = Sig.get_signal_state(comp)
        bars_held = state["bars_held"]
        since     = comp.index[-bars_held] if 0 < bars_held <= len(comp) else comp.index[-1]
        return {
            "signal": state["signal"],
            "score":  state["score"],
            "arrow":  _arrow(state["slope"]),
            "since":  since.strftime("%b %d"),
        }
    except Exception:
        return None


def _divergences(comp: pd.DataFrame, interval: str) -> list[dict]:
    if comp is None or comp.empty:
        return []
    params  = DIVERGENCE_PARAMS[interval]
    cutoff  = pd.Timestamp.now() - pd.Timedelta(days=params["recency_days"])
    price   = comp["Close"].values.astype(float)

    inds = {}
    if "RSI" in comp.columns:
        inds["RSI"] = comp["RSI"].values.astype(float)
    if "OBV" in comp.columns:
        inds["OBV"] = comp["OBV"].values.astype(float)
    score_s = Sig.score_series_full(comp)
    if len(score_s) == len(comp):
        inds["Score"] = score_s.values.astype(float)

    results = []
    for name, vals in inds.items():
        try:
            divs = find_regular_divergences(
                price, vals,
                left=params["left"], right=params["right"],
                match_window=params["match_window"],
            )
            for d in divs:
                if d["pi2"] < len(comp):
                    dt = comp.index[d["pi2"]]
                    if hasattr(dt, "to_pydatetime"):
                        dt = dt.to_pydatetime()
                    if pd.Timestamp(dt) >= cutoff:
                        results.append({
                            "indicator": name,
                            "type":      d["type"],       # "bullish" | "bearish"
                            "timeframe": _IV_LABEL[interval],
                            "date":      pd.Timestamp(dt).strftime("%b %d"),
                        })
        except Exception:
            pass
    return results


# Main scan

def generate_report(progress_cb=None) -> list[dict]:
    """
    Scan every ticker across all four timeframes.
    Returns a list of row dicts sorted by confluence (most BULL first).
    progress_cb(done, total, msg) if provided.
    """
    # Build symbol -> display mapping (short key for TICKERS, symbol for WATCHLIST)
    sym_map: dict[str, str] = {}
    for key, sym in TICKERS.items():
        sym_map[sym] = key
    for entries in WATCHLIST.values():
        for sym in entries:
            if sym not in sym_map:
                sym_map[sym] = sym

    symbols = list(sym_map.keys())
    total   = len(symbols)

    if progress_cb:
        progress_cb(0, total, "Fetching data…")

    d_batch  = Data.fetch_symbols_batch(symbols, "1d")
    w_batch  = Data.fetch_symbols_batch(symbols, "1wk")
    h3_batch = Data.fetch_symbols_batch(symbols, "3h")
    d3_batch = Data.fetch_symbols_batch(symbols, "3d")

    batches = {"1d": d_batch, "1wk": w_batch, "3h": h3_batch, "3d": d3_batch}

    rows = []
    for i, sym in enumerate(symbols):
        if progress_cb:
            progress_cb(i + 1, total, f"Processing {sym}…")

        daily_raw = d_batch.get(sym)
        if daily_raw is None or daily_raw.empty:
            continue

        weekly_raw = w_batch.get(sym)
        weekly     = weekly_raw if (weekly_raw is not None and not weekly_raw.empty) else daily_raw

        # Compute indicators per interval
        comps: dict[str, pd.DataFrame | None] = {}
        for iv in INTERVALS:
            base = batches[iv].get(sym)
            if base is None or base.empty:
                comps[iv] = None
                continue
            try:
                comps[iv] = indicators.compute_all(base, weekly)
            except Exception:
                comps[iv] = None

        # Price changes from raw daily closes
        closes = daily_raw["Close"].dropna()
        c0     = float(closes.iloc[-1]) if len(closes) >= 1 else None

        def _chg(n):
            if c0 is None or len(closes) < n + 1:
                return None
            prev = float(closes.iloc[-(n + 1)])
            return (c0 / prev - 1) * 100 if prev else None

        chg_1d = _chg(1)
        chg_1w = _chg(5)
        chg_1m = _chg(21)

        # Distance from 200D SMA
        dist_200d = None
        dc = comps.get("1d")
        if dc is not None and "SMA_200" in dc.columns and c0:
            s200 = dc["SMA_200"].dropna()
            if len(s200):
                v = float(s200.iloc[-1])
                dist_200d = (c0 / v - 1) * 100 if v else None

        # Signals + divergences per interval
        sigs  = {iv: _signal_row(comps[iv]) for iv in INTERVALS}
        divs  = []
        for iv in INTERVALS:
            divs.extend(_divergences(comps[iv], iv))

        bull_count = sum(1 for iv in INTERVALS if sigs[iv] and sigs[iv]["signal"] == "BULL")
        bear_count = sum(1 for iv in INTERVALS if sigs[iv] and sigs[iv]["signal"] == "BEAR")
        score_1d   = sigs["1d"]["score"] if sigs["1d"] else 0

        rows.append({
            "sym":       sym,
            "display":   sym_map[sym],
            "price":     c0,
            "chg_1d":    chg_1d,
            "chg_1w":    chg_1w,
            "chg_1m":    chg_1m,
            "dist_200d": dist_200d,
            "signals":   sigs,
            "divs":      divs,
            "bull_count": bull_count,
            "bear_count": bear_count,
            "score_1d":  score_1d,
        })

    rows.sort(key=lambda r: (-r["bull_count"], r["bear_count"], -r["score_1d"]))
    return rows


# HTML renderer

_BULL_BG = "#1a3a2a"; _BULL_FG = "#4ade80"
_BEAR_BG = "#3a1a1a"; _BEAR_FG = "#f87171"
_NEUT_BG = "#2a2a2a"; _NEUT_FG = "#9ca3af"
_DIV_BULL_BG = "#1a3a2a"; _DIV_BULL_FG = "#4ade80"
_DIV_BEAR_BG = "#3a1a1a"; _DIV_BEAR_FG = "#f87171"


def _sig_cell(sig: dict | None) -> str:
    if sig is None:
        return '<td class="sig neut">—</td>'
    s = sig["signal"]
    css = "bull" if s == "BULL" else ("bear" if s == "BEAR" else "neut")
    score = f'+{sig["score"]}' if sig["score"] >= 0 else str(sig["score"])
    return (
        f'<td class="sig {css}">'
        f'<span class="sig-top">{s} {score} {sig["arrow"]}</span>'
        f'<span class="sig-since">since {sig["since"]}</span>'
        f'</td>'
    )


def _dots(row: dict) -> str:
    sigs = row["signals"]
    html = '<span class="dots">'
    for iv in INTERVALS:
        sig = sigs[iv]
        s   = sig["signal"] if sig else "NEUTRAL"
        cls = "bull" if s == "BULL" else ("bear" if s == "BEAR" else "neut")
        html += f'<span class="dot {cls}" title="{_IV_LABEL[iv]}: {s}"></span>'
    html += "</span>"
    return html


def _div_cell(divs: list[dict], indicator: str) -> str:
    """TD for one indicator's divergences across all timeframes."""
    filtered = [d for d in divs if d["indicator"] == indicator]
    if not filtered:
        return '<td class="div-cell"><span class="muted">—</span></td>'
    badges = []
    for d in filtered:
        cls   = "div-bull" if d["type"] == "bullish" else "div-bear"
        arrow = "↑" if d["type"] == "bullish" else "↓"
        badges.append(f'<span class="{cls}">{arrow} {d["timeframe"]} {d["date"]}</span>')
    return f'<td class="div-cell">{"".join(badges)}</td>'


def _pct_cell(val, label="") -> str:
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return f'<td class="num muted">—</td>'
    color = _BULL_FG if val >= 0 else _BEAR_FG
    s = f'+{val:.1f}%' if val >= 0 else f'{val:.1f}%'
    return f'<td class="num" style="color:{color}">{s}</td>'


def build_report_html(rows: list[dict]) -> str:
    generated = datetime.now().strftime("%b %d, %Y  %H:%M")

    css = f"""
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
        background: #1a1a1a; color: #e0e0e0;
        font-family: 'Segoe UI', sans-serif; font-size: 12px;
        padding: 12px;
    }}
    .meta {{ color: #666; font-size: 11px; margin-bottom: 10px; }}
    table {{
        width: 100%; border-collapse: collapse;
        table-layout: fixed;
    }}
    th {{
        background: #242424; color: #888; font-size: 10px; font-weight: 600;
        text-transform: uppercase; letter-spacing: .04em;
        padding: 7px 8px; border-bottom: 1px solid #333;
        position: sticky; top: 0; z-index: 2;
        white-space: nowrap;
    }}
    td {{
        padding: 6px 8px; border-bottom: 1px solid #252525;
        vertical-align: middle;
    }}
    tr:hover td {{ background: #212121; }}
    .ticker {{ font-weight: 700; font-size: 12px; white-space: nowrap; }}
    .num {{ text-align: right; font-family: Consolas, monospace; white-space: nowrap; }}
    .muted {{ color: #555; }}
    /* Signal cells */
    .sig {{ text-align: center; min-width: 110px; }}
    .sig.bull {{ background: {_BULL_BG}; }}
    .sig.bear {{ background: {_BEAR_BG}; }}
    .sig.neut {{ background: {_NEUT_BG}; color: {_NEUT_FG}; }}
    .sig-top {{
        display: block; font-weight: 700; font-family: Consolas, monospace;
        font-size: 11px;
        color: inherit;
    }}
    .sig.bull .sig-top {{ color: {_BULL_FG}; }}
    .sig.bear .sig-top {{ color: {_BEAR_FG}; }}
    .sig-since {{
        display: block; font-size: 10px; color: #888; margin-top: 2px;
    }}
    /* Confluence dots */
    .dots {{ display: flex; gap: 4px; align-items: center; }}
    .dot {{
        width: 9px; height: 9px; border-radius: 50%; display: inline-block;
    }}
    .dot.bull {{ background: {_BULL_FG}; }}
    .dot.bear {{ background: {_BEAR_FG}; }}
    .dot.neut {{ background: #444; }}
    /* Divergence badges */
    .div-cell {{ vertical-align: middle; }}
    .div-bull {{
        display: inline-block; background: {_DIV_BULL_BG}; color: {_DIV_BULL_FG};
        border-radius: 4px; padding: 1px 6px; font-size: 10px;
        white-space: nowrap; margin: 1px 1px 1px 0;
    }}
    .div-bear {{
        display: inline-block; background: {_DIV_BEAR_BG}; color: {_DIV_BEAR_FG};
        border-radius: 4px; padding: 1px 6px; font-size: 10px;
        white-space: nowrap; margin: 1px 1px 1px 0;
    }}
    /* Column widths */
    .col-dots   {{ width: 54px; }}
    .col-ticker {{ width: 68px; }}
    .col-price  {{ width: 78px; }}
    .col-chg    {{ width: 58px; }}
    .col-200d   {{ width: 70px; }}
    .col-sig    {{ width: 118px; }}
    .col-div    {{ width: 110px; }}
    """

    header = """
    <tr>
      <th class="col-dots"></th>
      <th class="col-ticker">Ticker</th>
      <th class="col-price num">Price</th>
      <th class="col-chg num">1D%</th>
      <th class="col-chg num">1W%</th>
      <th class="col-chg num">1M%</th>
      <th class="col-200d num">vs 200D</th>
      <th class="col-sig">3H</th>
      <th class="col-sig">1D</th>
      <th class="col-sig">3D</th>
      <th class="col-sig">1W</th>
      <th class="col-div">RSI Div</th>
      <th class="col-div">OBV Div</th>
      <th class="col-div">Score Div</th>
    </tr>
    """

    body_rows = []
    for r in rows:
        body_rows.append(f"""
    <tr>
      <td class="col-dots">{_dots(r)}</td>
      <td class="ticker">{r["display"]}</td>
      <td class="num">{_price_str(r["price"])}</td>
      {_pct_cell(r["chg_1d"])}
      {_pct_cell(r["chg_1w"])}
      {_pct_cell(r["chg_1m"])}
      {_pct_cell(r["dist_200d"])}
      {_sig_cell(r["signals"]["3h"])}
      {_sig_cell(r["signals"]["1d"])}
      {_sig_cell(r["signals"]["3d"])}
      {_sig_cell(r["signals"]["1wk"])}
      {_div_cell(r["divs"], "RSI")}
      {_div_cell(r["divs"], "OBV")}
      {_div_cell(r["divs"], "Score")}
    </tr>""")

    body = "\n".join(body_rows)

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>{css}</style>
</head>
<body>
<p class="meta">Generated {generated} &nbsp;·&nbsp; {len(rows)} tickers &nbsp;·&nbsp; sorted by confluence</p>
<div style="overflow-x:auto;">
<table>
  <thead>{header}</thead>
  <tbody>{body}</tbody>
</table>
</div>
</body>
</html>"""
