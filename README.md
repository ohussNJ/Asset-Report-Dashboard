# Asset Report Dashboard

A desktop GUI that pulls live market data and displays a full indicator dashboard for a configurable watchlist

---

## First-Time Setup (Windows)

### 1. Install Python

1. Go to **https://www.python.org/downloads**
2. Download **Python 3.12.x** (Windows installer 64-bit)
   - **Do not use Python 3.14+** — a required library (pandas-ta) does not support it yet

### 2. Download this project

If you download this as a ZIP file, extract it to a folder (e.g. `C:\AssetReport`).

### 3. Install dependencies

Open **Command Prompt** or **PowerShell**, navigate to the project folder, and run:

```
cd C:\AssetReport
python -m pip install -r requirements.txt
```

### 4. Run the app

**Option A — open launcher**
- Run `AssetReport.bat` 

**Option B — from the terminal**
```
python main.py
```

---

## Interface overview


### Summary tab

A responsive grid of cards — one per ticker, sorted by score (highest first). Each card shows:
- **BULL** (green) / **BEAR** (red) header, or neutral (gray, no label)
- Current price and percentage change from the previous close
- Score sparkline (last 60 bars) with ±20 neutral-zone shading
- Per-indicator breakdown across momentum, trend, structure, volume, and channels sections

Clicking a card navigates to that ticker's chart tab. A scrolling banner at the top shows all bullish tickers and their scores.

### Watchlist tab

All tracked symbols grouped by category (Equities, ETFs, Crypto, Commodities), sorted by score within each group. Each row shows the symbol, name, current price, % change, signal score badge, and a button to open that ticker as a chart tab. Expand any row with the ▼ button to see the full indicator card inline.

### Per-ticker chart tabs

Each ticker has its own tab with six sub-chart tabs:

| Tab | Price panel | Indicator panel |
|-----|-------------|-----------------|
| **Volume** | Candlestick + EMA/SMA 50/100/200 + KC + NW + Bull Band | Volume bars + Volume MA |
| **Score** | Same as Volume | Smoothed score line with BULL/BEAR fill zones |
| **RSI** | Same as Volume | RSI(14) + RSI MA, OB/OS zones, divergence lines |
| **Stoch RSI** | Same as Volume | Slow StochRSI (3,3,14,14) and Fast StochRSI (3,3,6,9) |
| **OBV** | Same as Volume | OBV + OBV EMA, bull/bear fill, divergence lines |
| **Keltner** | Candlestick + Keltner Channel + NW Envelope (dotted) + 17-bar (purple) and 42-bar (blue) reference lines | CNV_TB histogram (blue above zero, red below) with B/S crossover markers |

Use the **matplotlib toolbar** at the top of each chart to zoom, pan, and export as an image.

---

## Indicators reference

### Scored indicators (contribute to the overall signal)

| Indicator | Parameters | Bull condition | Bear condition | Max points |
|-----------|-----------|----------------|----------------|------------|
| RSI | Period 14, MA 14 | Slope↑ AND RSI > MA; OR RSI ≥ 56 | Slope↓ AND RSI < MA; OR RSI ≤ 36 | ±20 |
| Ichimoku Cloud | Conv 9, Base 26, SpanB 52 | Price above cloud top | Price below cloud bottom | ±10 |
| Ichimoku Base | Base 26 | Price above base line | Price below base line | ±10 |
| EMA 50/200 | Periods 50, 200 | Price above both | Price below both | ±10 |
| SMA 50/200 | Periods 50, 200 | Price above both | Price below both | ±10 |
| Keltner Channel | EMA 20, ATR 10, scalar 2× | Price above upper AND band widening | Price below lower AND band widening | ±10 |
| OBV | EMA 20, slope 20 bars | OBV > EMA AND slope↑ | OBV < EMA AND slope↓ | ±10 |
| CNV | SMA 20 | CNV above its MA | CNV below its MA | ±10 |

**Total possible: ±70**

### Visual-only indicators (not scored)

| Indicator | Description |
|-----------|-------------|
| StochRSI (slow) | K(3,3,14,14) vs D line — shown on the Stoch RSI tab |
| StochRSI (fast) | K(3,3,6,9) vs D line — shown on the Stoch RSI tab |
| Bull Market Support Band | 20w SMA + 21w EMA — always sourced from weekly data regardless of interval |
| NW Envelope | Nadaraya-Watson kernel regression (LuxAlgo repainting mode) — upper band green dotted, lower red dotted |
| Divergences | Regular bullish/bearish divergences drawn on RSI, Score, and OBV charts |

### Signal classification

The raw score is smoothed with a 5-bar SMA. State changes require both a threshold cross and a confirming slope (hysteresis prevents flip-flopping):

| State | Entry | Exit to Neutral |
|-------|-------|----------------|
| **BULL** | Smoothed score > +30 AND 5-bar slope > 0 | Smoothed score drops below +10 |
| **BEAR** | Smoothed score < −30 AND 5-bar slope < 0 | Smoothed score rises above −10 |
| **NEUTRAL** | Default state | — |

---

## Data source

Market data is pulled from **Yahoo Finance** via the `yfinance` library — free, no API key required.

- **Daily data**: 2 years of history fetched on launch
- **Weekly data**: 5 years of history (needed for 200-week MAs and Bull Market Support Band)
- Prices are **split and dividend adjusted** automatically
- Data is **end-of-day**, not real-time — crypto (BTC/ETH) ticks 24/7 so has no weekend gaps

---

## Troubleshooting

**"python is not recognized"**
Python was not added to PATH during install. Uninstall Python and reinstall — make sure to tick **"Add python.exe to PATH"** on the first installer screen.

**"Cannot install on Python version 3.14" or similar**
Python 3.14+ is not yet supported by `pandas-ta`. Install **Python 3.12.x** instead (see setup step 1). You can have multiple Python versions installed side by side — use `py -3.12 main.py` to run with the correct one, and update `AssetReport.bat` accordingly.

**"No module named yfinance" (or any other module)**
Dependencies were not installed, or were installed for a different Python version. Run:
```
py -3.12 -m pip install -r requirements.txt
```

**yfinance stops returning data / throws an error**
Yahoo Finance occasionally changes their backend, which breaks yfinance. The fix is almost always just updating the library:
```
py -3.12 -m pip install --upgrade yfinance
```
If that doesn't work, check for a newer release at https://github.com/ranaroussi/yfinance

**Data shows N/A for some indicators**
Normal for the first few bars of a series due to indicator warm-up periods (e.g. a 200-period EMA needs 200 bars before it has a value).

**App is slow to open**
On first launch it fetches 2 years of daily + 5 years of weekly data for all tickers. Subsequent refreshes use a 4-hour disk cache so they're faster.

**No internet connection**
The app requires internet access to fetch prices. It will show an error in the status bar if data cannot be retrieved.
