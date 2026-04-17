# backtest.py  –  Signal state machine backtester

import numpy as np
import pandas as pd
from signals import signal_state_history

INITIAL = 1_000.0


def _position_series(states: pd.Series, hold_through_neutral: bool) -> pd.Series:
    """
    Derive a per-bar position from the state series.

    hold_through_neutral=False  (Buy on Bull):
        LONG when state == BULL, FLAT otherwise.

    hold_through_neutral=True   (Buy Bull / Sell Bear):
        Enter LONG on BULL, hold through NEUTRAL, exit on BEAR.
        NEUTRAL does not change the position.
    """
    if not hold_through_neutral:
        return states.map({"BULL": "LONG", "NEUTRAL": "FLAT", "BEAR": "FLAT"})

    positions = []
    pos = "FLAT"
    for state in states:
        if state == "BULL":
            pos = "LONG"
        elif state == "BEAR":
            pos = "FLAT"
        # NEUTRAL: keep current pos
        positions.append(pos)
    return pd.Series(positions, index=states.index)


def run_backtest(df: pd.DataFrame, entry: int = 30, exit_th: int = 10,
                 slope_bars: int = 5, hold_through_neutral: bool = False) -> dict:
    """
    Replay the signal state machine over df with custom parameters.
    Equity starts at $1,000. Signal fires at bar close, position taken next bar.
    """
    states = signal_state_history(df, n=len(df), entry=entry,
                                   exit_th=exit_th, slope_bars=slope_bars)
    if len(states) < 2:
        return {}

    closes    = df["Close"].reindex(states.index).ffill()
    daily_ret = closes.pct_change().fillna(0)

    # Position at bar T is determined by state at T-1 (signal fires at close T-1)
    pos       = _position_series(states, hold_through_neutral)
    prev_pos  = pos.shift(1).fillna("FLAT")

    strat_ret = pd.Series(0.0, index=states.index)
    strat_ret[prev_pos == "LONG"] = daily_ret[prev_pos == "LONG"]

    equity = INITIAL * (1 + strat_ret).cumprod()
    bh     = INITIAL * (1 + daily_ret).cumprod()

    # ── Trades (based on position transitions) ────────────────────────────────
    trades     = []
    in_trade   = False
    entry_date = entry_price = None

    for i in range(1, len(pos)):
        prev_p = pos.iloc[i - 1]
        cur_p  = pos.iloc[i]
        date   = pos.index[i]
        price  = float(closes.iloc[i])

        if not in_trade and prev_p == "FLAT" and cur_p == "LONG":
            in_trade, entry_date, entry_price = True, date, price
        elif in_trade and prev_p == "LONG" and cur_p == "FLAT":
            trades.append({
                "entry_date":  entry_date,
                "exit_date":   date,
                "entry_price": entry_price,
                "exit_price":  price,
                "return":      price / entry_price - 1,
                "open":        False,
            })
            in_trade = False

    if in_trade:
        price = float(closes.iloc[-1])
        trades.append({
            "entry_date":  entry_date,
            "exit_date":   pos.index[-1],
            "entry_price": entry_price,
            "exit_price":  price,
            "return":      price / entry_price - 1,
            "open":        True,
        })

    # ── Stats ─────────────────────────────────────────────────────────────────
    total_return = float(equity.iloc[-1] / INITIAL - 1)
    bh_return    = float(bh.iloc[-1]     / INITIAL - 1)

    rolling_max = equity.cummax()
    drawdown    = (equity - rolling_max) / rolling_max
    max_dd      = float(drawdown.min())

    winning  = [t for t in trades if t["return"] > 0]
    win_rate = len(winning) / len(trades) if trades else 0.0

    sharpe = 0.0
    if strat_ret.std() > 0:
        sharpe = float((strat_ret.mean() / strat_ret.std()) * np.sqrt(252))

    return {
        "equity":       equity,
        "bh":           bh,
        "states":       states,
        "position":     pos,
        "closes":       closes,
        "trades":       trades,
        "total_return": total_return,
        "bh_return":    bh_return,
        "max_drawdown": max_dd,
        "win_rate":     win_rate,
        "sharpe":       sharpe,
        "n_trades":     len(trades),
    }
