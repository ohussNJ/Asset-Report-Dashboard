# Market Signal Platform

A financial market service (equities, crypto, commodities) that fetches live data, displays full indicator breakdown, and generates signal scoring for a configurable watchlist

**Stack:** FastAPI · React + Vite + TypeScript · TradingView Lightweight Charts · Redis · PostgreSQL · Celery · Docker

---

## Setup

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/)

### 1. Create a `.env` file

In the project root, create a file named `.env` with the following contents:

```
POSTGRES_USER=assetreport
POSTGRES_PASSWORD=assetreport
POSTGRES_DB=assetreport
DATABASE_URL=postgresql://assetreport:assetreport@postgres:5432/assetreport
REDIS_URL=redis://redis:6379/0
```

### 2. Start the app

```
docker compose up --build
```

This starts five services: `redis`, `postgres`, `app` (FastAPI), `worker` (Celery), and `frontend` (Nginx).

On first run the Celery worker fetches 2 years of daily and 5 years of weekly data for all tickers. This takes about a minute.

Open **http://localhost:3000** in your browser.

---

## Interface

### Summary tab

A grid of cards, one per ticker, sorted by score. Each card shows:
- **BULL** / **BEAR** signal badge or neutral state
- Current price and percentage change from the previous close
- Score sparkline (last 60 bars) with neutral-zone shading
- Per-indicator breakdown across momentum, trend, structure, volume, and channel sections

### Watchlist tab

All tracked symbols grouped by category (Equities, ETFs, Crypto, Commodities) and sorted by score within each group. Each row shows the symbol, name, price, % change, and signal badge. Expand any row to see the full indicator card. You can add new symbols to the watchlist from this tab.

### Charts tab

Per-ticker TradingView charts with interval and lookback controls. Includes price candles, moving averages, Keltner Channel, NW Envelope, Bull Market Band, RSI, StochRSI, OBV, Score, and CNV. Divergence lines are drawn on RSI, OBV, and Score panels.

### Alerts tab

Create price or signal alerts for any symbol. Alerts fire via browser notification when the Celery worker detects the condition during its next scheduled run.

### Info tab

Full indicator parameters and signal classification reference table

---

## Indicators

### Scored indicators

| Indicator | Parameters | Bull condition | Bear condition | Points |
|-----------|-----------|----------------|----------------|--------|
| RSI | Period 14  MA 14 | Slope > 0 AND RSI > MA; OR RSI >= 56 | Slope <= 0 AND RSI < MA; OR RSI <= 36 | ±20 |
| Ichimoku Cloud | Conv 9  Base 26  SpanB 52 | Price above cloud top | Price below cloud bottom | ±5 |
| Ichimoku Base | Base 26 | Price above base line | Price below base line | ±5 |
| EMA 50/200 | Periods 50 and 200 | Price above both | Price below both | ±5 |
| SMA 50/200 | Periods 50 and 200 | Price above both | Price below both | ±5 |
| Keltner Channel | EMA 20  ATR 10  scalar 2x | Price above upper AND band widening | Price below lower AND band widening | ±10 |
| OBV | EMA 20  slope 20 bars | OBV > EMA AND slope > 0 | OBV < EMA AND slope <= 0 | ±10 |
| CNV | SMA 20 | CNV above its MA | CNV below its MA | ±10 |

**Total possible: ±70**

### Visual-only indicators

| Indicator | Description |
|-----------|-------------|
| StochRSI (slow) | K(3,3,14,14) vs D line |
| StochRSI (fast) | K(3,3,6,9) vs D line |
| Bull Market Band | 20w SMA + 21w EMA sourced from weekly data |
| NW Envelope | Nadaraya-Watson kernel regression (LuxAlgo repainting mode) |
| Divergences | Regular bullish/bearish divergences on RSI, Score, and OBV |

### Signal classification

The raw score is smoothed with a 5-bar SMA. State transitions require both a threshold cross and a confirming slope:

| State | Entry | Exit to Neutral |
|-------|-------|----------------|
| **BULL** | Smoothed score > +30 AND 5-bar slope > 0 | Score drops below +10 |
| **BEAR** | Smoothed score < -30 AND 5-bar slope < 0 | Score rises above -10 |
| **NEUTRAL** | Default | — |

---

## Data

Market data is pulled from Yahoo Finance via `yfinance`. No API key required.

- **Daily bars**: 2 years of history
- **Weekly bars**: 5 years of history (needed for 20w/21w Bull Band and longer MAs)
- Prices are split and dividend adjusted
- Data is end of day. Crypto has no weekend gaps.
- The Celery worker re-fetches daily data on weekdays at 4:30 PM ET and weekly data Sunday morning. Any open browser tab refreshes automatically via WebSocket.

---

## Troubleshooting

**App shows no data on first load**
The worker fetches on startup. Wait about 60 seconds then reload.

**yfinance throws errors**
Yahoo Finance occasionally changes its backend. Update the library:
```
docker compose exec worker pip install --upgrade yfinance
```

**N/A for some indicators**
Normal for the first bars of a series due to indicator warm-up (e.g. EMA 200 needs 200 bars).
