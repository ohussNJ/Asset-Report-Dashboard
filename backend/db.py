# db.py  –  SQLAlchemy models and PostgreSQL helpers

import math
import os
from datetime import datetime, timezone

import pandas as pd
from sqlalchemy import Boolean, Column, Date, DateTime, Float, Integer, String, UniqueConstraint, create_engine, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import DeclarativeBase, Session

_DATABASE_URL = os.getenv("DATABASE_URL", "")

_engine = None


def _get_engine():
    global _engine
    if _engine is not None:
        return _engine
    url = _DATABASE_URL
    if not url:
        return None
    # SQLAlchemy 2.x requires the +psycopg2 dialect suffix
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    try:
        _engine = create_engine(url, pool_pre_ping=True)
        return _engine
    except Exception as exc:
        print(f"[db] engine creation failed: {exc}")
        return None


# ── Models ─────────────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


class PriceData(Base):
    __tablename__ = "price_data"
    id       = Column(Integer, primary_key=True)
    symbol   = Column(String, nullable=False)
    interval = Column(String, nullable=False)
    date     = Column(Date, nullable=False)
    open     = Column(Float)
    high     = Column(Float)
    low      = Column(Float)
    close    = Column(Float)
    volume   = Column(Float)
    __table_args__ = (
        UniqueConstraint("symbol", "interval", "date", name="uq_price_symbol_interval_date"),
    )


class Alert(Base):
    __tablename__ = "alerts"
    id             = Column(Integer, primary_key=True)
    symbol         = Column(String, nullable=False)
    condition_type = Column(String, nullable=False)
    threshold      = Column(Float, nullable=True)
    triggered      = Column(Boolean, default=False, nullable=False)
    created_at     = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    triggered_at   = Column(DateTime(timezone=True), nullable=True)


class SignalHistory(Base):
    __tablename__ = "signal_history"
    id       = Column(Integer, primary_key=True)
    symbol   = Column(String, nullable=False)
    interval = Column(String, nullable=False)
    date     = Column(Date, nullable=False)
    signal   = Column(String)
    score    = Column(Float)
    __table_args__ = (
        UniqueConstraint("symbol", "interval", "date", name="uq_signal_symbol_interval_date"),
    )


# ── Init ───────────────────────────────────────────────────────────────────────

def init_db() -> None:
    engine = _get_engine()
    if engine is None:
        return
    try:
        Base.metadata.create_all(engine)
        print("[db] tables ready")
    except Exception as exc:
        # Race condition: app and worker both call init_db on startup
        # so if the table was created by the other process first that is fine
        msg = str(exc)
        if "already exists" in msg or "duplicate key" in msg:
            print("[db] tables already exist")
        else:
            print(f"[db] init_db error: {exc}")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _safe_float(val) -> float | None:
    if val is None:
        return None
    try:
        f = float(val)
        return None if math.isnan(f) else f
    except Exception:
        return None


# ── Price data ─────────────────────────────────────────────────────────────────

def upsert_prices(symbol: str, interval: str, df: pd.DataFrame) -> None:
    engine = _get_engine()
    if engine is None or df.empty:
        return
    rows = [
        {
            "symbol":   symbol,
            "interval": interval,
            "date":     pd.Timestamp(dt).date(),
            "open":     _safe_float(row.get("Open")),
            "high":     _safe_float(row.get("High")),
            "low":      _safe_float(row.get("Low")),
            "close":    _safe_float(row.get("Close")),
            "volume":   _safe_float(row.get("Volume")),
        }
        for dt, row in df.iterrows()
    ]
    if not rows:
        return
    try:
        stmt = pg_insert(PriceData).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["symbol", "interval", "date"],
            set_={
                "open":   stmt.excluded.open,
                "high":   stmt.excluded.high,
                "low":    stmt.excluded.low,
                "close":  stmt.excluded.close,
                "volume": stmt.excluded.volume,
            },
        )
        with engine.begin() as conn:
            conn.execute(stmt)
    except Exception as exc:
        print(f"[db] upsert_prices error ({symbol} {interval}): {exc}")


def read_prices(symbol: str, interval: str) -> pd.DataFrame:
    engine = _get_engine()
    if engine is None:
        return pd.DataFrame()
    try:
        with Session(engine) as session:
            rows = (
                session.query(PriceData)
                .filter_by(symbol=symbol, interval=interval)
                .order_by(PriceData.date)
                .all()
            )
            if not rows:
                return pd.DataFrame()
            data = {
                "Open":   [r.open   for r in rows],
                "High":   [r.high   for r in rows],
                "Low":    [r.low    for r in rows],
                "Close":  [r.close  for r in rows],
                "Volume": [r.volume for r in rows],
            }
            index = pd.to_datetime([r.date for r in rows])
        return pd.DataFrame(data, index=index)
    except Exception as exc:
        print(f"[db] read_prices error ({symbol} {interval}): {exc}")
        return pd.DataFrame()


# ── Alerts ─────────────────────────────────────────────────────────────────────

def _alert_to_dict(r: Alert) -> dict:
    return {
        "id":             r.id,
        "symbol":         r.symbol,
        "condition_type": r.condition_type,
        "threshold":      r.threshold,
        "triggered":      r.triggered,
        "created_at":     r.created_at.isoformat() if r.created_at else None,
        "triggered_at":   r.triggered_at.isoformat() if r.triggered_at else None,
    }


def list_alerts() -> list[dict]:
    engine = _get_engine()
    if engine is None:
        return []
    try:
        with Session(engine) as session:
            rows = session.query(Alert).order_by(Alert.created_at.desc()).all()
            return [_alert_to_dict(r) for r in rows]
    except Exception as exc:
        print(f"[db] list_alerts error: {exc}")
        return []


def create_alert(symbol: str, condition_type: str, threshold: float | None) -> dict:
    engine = _get_engine()
    if engine is None:
        raise RuntimeError("Database not available")
    try:
        with Session(engine) as session:
            alert = Alert(symbol=symbol, condition_type=condition_type, threshold=threshold)
            session.add(alert)
            session.commit()
            session.refresh(alert)
            return _alert_to_dict(alert)
    except Exception as exc:
        print(f"[db] create_alert error: {exc}")
        raise


def delete_alert(alert_id: int) -> bool:
    engine = _get_engine()
    if engine is None:
        raise RuntimeError("Database not available")
    try:
        with Session(engine) as session:
            row = session.query(Alert).filter(Alert.id == alert_id).first()
            if row is None:
                return False
            session.delete(row)
            session.commit()
            return True
    except Exception as exc:
        print(f"[db] delete_alert error: {exc}")
        raise


def get_latest_price_date():
    """Return the most recent date in price_data (1d interval), or None if empty."""
    engine = _get_engine()
    if engine is None:
        return None
    try:
        with Session(engine) as session:
            return session.query(func.max(PriceData.date)).filter(PriceData.interval == "1d").scalar()
    except Exception as exc:
        print(f"[db] get_latest_price_date error: {exc}")
        return None


def list_untriggered_alerts() -> list[dict]:
    engine = _get_engine()
    if engine is None:
        return []
    try:
        with Session(engine) as session:
            rows = session.query(Alert).filter(Alert.triggered == False).all()
            return [_alert_to_dict(r) for r in rows]
    except Exception as exc:
        print(f"[db] list_untriggered_alerts error: {exc}")
        return []


def mark_alert_triggered(alert_id: int) -> dict | None:
    engine = _get_engine()
    if engine is None:
        return None
    try:
        with Session(engine) as session:
            row = session.query(Alert).filter(Alert.id == alert_id).first()
            if row is None:
                return None
            row.triggered    = True
            row.triggered_at = datetime.now(timezone.utc)
            session.commit()
            session.refresh(row)
            return _alert_to_dict(row)
    except Exception as exc:
        print(f"[db] mark_alert_triggered error: {exc}")
        return None
