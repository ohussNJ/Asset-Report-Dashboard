# worker.py  –  Celery worker + beat scheduler

import json
import os
import time
from datetime import datetime, timezone, timedelta, date as date_type

import redis as redis_lib
from celery import Celery
from celery.schedules import crontab
from celery.signals import worker_ready

import data as Data
import db
import indicators
import signals as Sig
from config import TICKERS, WATCHLIST

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery("asset_report", broker=REDIS_URL, backend=REDIS_URL)

celery_app.conf.timezone = "UTC"
celery_app.conf.beat_schedule = {
    # Mon-Fri at 9:30 PM UTC = 4:30 PM ET (EDT); 10:30 PM UTC in EST (close enough)
    "fetch-daily": {
        "task": "worker.fetch_daily",
        "schedule": crontab(hour=21, minute=30, day_of_week="1-5"),
    },
    # Sunday 2 AM UTC = Saturday 10 PM ET (weekly bar refresh)
    "fetch-weekly": {
        "task": "worker.fetch_weekly",
        "schedule": crontab(hour=2, minute=0, day_of_week="0"),
    },
}


def _last_expected_trading_day() -> date_type:
    """Most recent weekday for which we should have a completed daily bar."""
    now  = datetime.now(timezone.utc)
    # market close publish happens at 21:30 UTC; before that, prior day is latest
    cutoff = now.replace(hour=21, minute=30, second=0, microsecond=0)
    day = now.date() if now >= cutoff else now.date() - timedelta(days=1)
    while day.weekday() >= 5:   # walk back over weekends
        day -= timedelta(days=1)
    return day


def _data_is_stale() -> bool:
    latest = db.get_latest_price_date()
    if latest is None:
        return True
    # sqlalchemy may return a date or datetime
    if hasattr(latest, "date"):
        latest = latest.date()
    return latest < _last_expected_trading_day()


@worker_ready.connect
def on_worker_ready(**kwargs) -> None:
    db.init_db()
    if _data_is_stale():
        print("[worker] stale data detected on startup, running fetch_daily")
        fetch_daily.delay()


def _publish(channel: str, payload: str) -> None:
    try:
        r = redis_lib.from_url(REDIS_URL)
        r.publish(channel, payload)
    except Exception as exc:
        print(f"[worker] publish error ({channel}): {exc}")


def _check_alerts(price_map: dict[str, float], signal_map: dict[str, str]) -> None:
    alerts = db.list_untriggered_alerts()
    if not alerts:
        return
    for alert in alerts:
        sym   = alert["symbol"]
        ctype = alert["condition_type"]
        fired = False
        if ctype == "price_above" and sym in price_map:
            fired = price_map[sym] >= alert["threshold"]
        elif ctype == "price_below" and sym in price_map:
            fired = price_map[sym] <= alert["threshold"]
        elif ctype == "signal_bull" and sym in signal_map:
            fired = signal_map[sym] == "BULL"
        elif ctype == "signal_bear" and sym in signal_map:
            fired = signal_map[sym] == "BEAR"
        if fired:
            updated = db.mark_alert_triggered(alert["id"])
            if updated:
                _publish("asset_report:alerts", json.dumps(updated))
                print(f"[worker] alert triggered: {sym} {ctype}")


@celery_app.task(name="worker.fetch_daily")
def fetch_daily() -> None:
    print("[worker] fetch_daily started")

    daily_data:  dict[str, object] = {}
    weekly_data: dict[str, object] = {}

    for interval in ("1d", "1wk"):
        try:
            result = Data.fetch_all(interval, force=True)
            for key, df in result.items():
                db.upsert_prices(TICKERS[key], interval, df)
                if interval == "1d":
                    daily_data[TICKERS[key]]  = df
                else:
                    weekly_data[TICKERS[key]] = df
            print(f"[worker] main tickers {interval} ok ({len(result)} symbols)")
        except Exception as exc:
            print(f"[worker] main tickers {interval} error: {exc}")
        time.sleep(2)

    main_syms = set(TICKERS.values())
    watchlist_syms = [
        s
        for entries in WATCHLIST.values()
        for s in entries
        if s not in main_syms
    ]

    for interval in ("1d", "1wk"):
        try:
            result = Data.fetch_symbols_batch(watchlist_syms, interval)
            for symbol, df in result.items():
                db.upsert_prices(symbol, interval, df)
                if interval == "1d":
                    daily_data[symbol]  = df
                else:
                    weekly_data[symbol] = df
            print(f"[worker] watchlist {interval} ok ({len(result)} symbols)")
        except Exception as exc:
            print(f"[worker] watchlist {interval} error: {exc}")
        time.sleep(2)

    # build maps for alert evaluation
    price_map:  dict[str, float] = {}
    signal_map: dict[str, str]   = {}
    for sym, df in daily_data.items():
        try:
            close = df["Close"].dropna()  # type: ignore[union-attr]
            if not close.empty:
                price_map[sym] = float(close.iloc[-1])
                dw = weekly_data.get(sym, df)
                comp = indicators.compute_all(df, dw if not dw.empty else df)  # type: ignore[union-attr]
                signal_map[sym] = Sig.get_signal_state(comp)["signal"]
        except Exception as exc:
            print(f"[worker] signal eval error ({sym}): {exc}")

    _check_alerts(price_map, signal_map)
    _publish("asset_report:refresh", "done")
    print("[worker] fetch_daily done")


@celery_app.task(name="worker.fetch_weekly")
def fetch_weekly() -> None:
    print("[worker] fetch_weekly started")

    try:
        result = Data.fetch_all("1wk", force=True)
        for key, df in result.items():
            db.upsert_prices(TICKERS[key], "1wk", df)
        print(f"[worker] main tickers 1wk ok ({len(result)} symbols)")
    except Exception as exc:
        print(f"[worker] main tickers 1wk error: {exc}")

    main_syms = set(TICKERS.values())
    watchlist_syms = [
        s
        for entries in WATCHLIST.values()
        for s in entries
        if s not in main_syms
    ]

    try:
        result = Data.fetch_symbols_batch(watchlist_syms, "1wk")
        for symbol, df in result.items():
            db.upsert_prices(symbol, "1wk", df)
        print(f"[worker] watchlist 1wk ok ({len(result)} symbols)")
    except Exception as exc:
        print(f"[worker] watchlist 1wk error: {exc}")

    _publish("asset_report:refresh", "done")
    print("[worker] fetch_weekly done")
