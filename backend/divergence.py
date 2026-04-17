# divergence.py  –  Pivot detection and regular divergence identification
# Built to support score, RSI, and OBV divergences.

import numpy as np


def find_pivots(series: np.ndarray, left: int = 5, right: int = 5):
    """
    Return indices of pivot highs and lows.
    A pivot high at i: series[i] is >= all values within left bars behind
    and right bars ahead. NaN bars are skipped.
    """
    highs, lows = [], []
    n = len(series)
    for i in range(left, n - right):
        v = series[i]
        if np.isnan(v):
            continue
        left_vals  = series[i - left : i]
        right_vals = series[i + 1 : i + right + 1]
        if np.any(np.isnan(left_vals)) or np.any(np.isnan(right_vals)):
            continue
        if v >= np.max(left_vals) and v >= np.max(right_vals):
            highs.append(i)
        if v <= np.min(left_vals) and v <= np.min(right_vals):
            lows.append(i)
    return highs, lows


def _nearest(pivot_list, target, window):
    """Return the pivot in pivot_list nearest to target within window bars, or None."""
    cands = [p for p in pivot_list if abs(p - target) <= window]
    if not cands:
        return None
    return min(cands, key=lambda p: abs(p - target))


def find_regular_divergences(
    price:     np.ndarray,
    indicator: np.ndarray,
    left:      int   = 5,
    right:     int   = 5,
    match_window: int = 8,         # bars to search for a matching indicator pivot
    min_price_pct: float = 0.3,    # min % move between price pivots
    min_ind_delta: float = 3.0,    # min absolute move between indicator pivots
):
    """
    Detect regular (classic) divergences between price and an indicator.

    Finds pivots on BOTH price and indicator independently, then matches each
    price pivot to the nearest indicator pivot within match_window bars. This
    ensures indicator panel markers land on the indicator's own turning points.

    Regular bearish : price makes higher high, indicator makes lower high
    Regular bullish : price makes lower low,   indicator makes higher low

    Returns a list of dicts:
        type         – 'bullish' or 'bearish'
        pi1, pi2     – price pivot bar indices   (for price panel)
        ii1, ii2     – indicator pivot bar indices (for indicator panel)
        p1, p2       – price values at pi1/pi2
        ind1, ind2   – indicator values at ii1/ii2
    """
    price_highs, price_lows   = find_pivots(price,     left, right)
    ind_highs,   ind_lows     = find_pivots(indicator, left, right)
    results = []

    # ── Regular bearish ───────────────────────────────────────────────────────
    for j in range(1, len(price_highs)):
        ph1, ph2 = price_highs[j - 1], price_highs[j]
        ih1 = _nearest(ind_highs, ph1, match_window)
        ih2 = _nearest(ind_highs, ph2, match_window)
        if ih1 is None or ih2 is None:
            continue
        if any(np.isnan(v) for v in [price[ph1], price[ph2], indicator[ih1], indicator[ih2]]):
            continue
        price_chg = (price[ph2] - price[ph1]) / price[ph1] * 100
        ind_chg   = indicator[ih2] - indicator[ih1]
        if price_chg >= min_price_pct and ind_chg <= -min_ind_delta:
            results.append({
                "type": "bearish",
                "pi1": ph1, "pi2": ph2,
                "ii1": ih1, "ii2": ih2,
                "p1": price[ph1],      "p2": price[ph2],
                "ind1": indicator[ih1], "ind2": indicator[ih2],
            })

    # ── Regular bullish ───────────────────────────────────────────────────────
    for j in range(1, len(price_lows)):
        pl1, pl2 = price_lows[j - 1], price_lows[j]
        il1 = _nearest(ind_lows, pl1, match_window)
        il2 = _nearest(ind_lows, pl2, match_window)
        if il1 is None or il2 is None:
            continue
        if any(np.isnan(v) for v in [price[pl1], price[pl2], indicator[il1], indicator[il2]]):
            continue
        price_chg = (price[pl2] - price[pl1]) / price[pl1] * 100
        ind_chg   = indicator[il2] - indicator[il1]
        if price_chg <= -min_price_pct and ind_chg >= min_ind_delta:
            results.append({
                "type": "bullish",
                "pi1": pl1, "pi2": pl2,
                "ii1": il1, "ii2": il2,
                "p1": price[pl1],      "p2": price[pl2],
                "ind1": indicator[il1], "ind2": indicator[il2],
            })

    return results
