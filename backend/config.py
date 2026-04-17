# config.py  –  All configuration for Asset Report Dashboard

# ── Tickers ────────────────────────────────────────────────────────────────────
TICKERS = {
    "SPY":  "SPY",
    "GLD":  "GLD",
    "NVDA": "NVDA",
    "BTC":  "BTC-USD",
    "ETH":  "ETH-USD",
}

# ── Watchlist ──────────────────────────────────────────────────────────────────
WATCHLIST = {
    "Equities": {
        "AAPL":  "Apple",
        "MSFT":  "Microsoft",
        "AMZN":  "Amazon",
        "GOOGL": "Alphabet",
        "META":  "Meta",
        "TSLA":  "Tesla",
        "COIN":  "Coinbase",
        "MSTR":  "MicroStrategy",
        "CRCL":  "Circle",
        "HOOD":  "Robinhood",
    },
    "ETFs": {
        "QQQ":  "Nasdaq 100",
        "IWM":  "Russell 2000",
        "SOXX": "Semiconductors",
        "XBI":  "Biotech",
        "XHB":  "Homebuilders",
        "XLB":  "Materials",
        "XLC":  "Communication Services",
        "XLE":  "Energy",
        "XLF":  "Financials",
        "XLI":  "Industrials",
        "XLK":  "Technology",
        "XLP":  "Consumer Staples",
        "XLRE": "Real Estate",
        "XLU":  "Utilities",
        "XLV":  "Health Care",
        "XLY":  "Consumer Discretionary",
        "UUP":  "US Dollar",
    },
    "Crypto": {
        "SOL-USD":  "Solana",
        "BNB-USD":  "BNB",
        "XRP-USD":  "XRP",
        "ADA-USD":  "Cardano",
        "LINK-USD": "Chainlink",
    },
    "Commodities": {
        "SLV":  "Silver",
        "USO":  "Oil (WTI)",
        "WEAT": "Wheat",
    },
}

# ── Data fetch ─────────────────────────────────────────────────────────────────
DAILY_PERIOD   = "2y"
WEEKLY_PERIOD  = "5y"   # need more history for 20w/200w MAs

# ── Chart lookback options ─────────────────────────────────────────────────────
LOOKBACK_OPTIONS = {
    "3M":  {"1d": 63,  "1wk": 13},
    "6M":  {"1d": 126, "1wk": 26},
    "9M":  {"1d": 189, "1wk": 39},
    "12M": {"1d": 252, "1wk": 52},
    "15M": {"1d": 315, "1wk": 65},
    "18M": {"1d": 378, "1wk": 78},
}
DEFAULT_LOOKBACK = {"1d": "6M", "1wk": "12M"}

# ── RSI ────────────────────────────────────────────────────────────────────────
RSI_PERIOD    = 14
RSI_MA_PERIOD = 14

# ── Stochastic RSI  (k, d, stoch_length, rsi_length) ──────────────────────────
STOCHRSI_CONFIGS = [
    {"label": "3,3,14,14", "k": 3, "d": 3, "length": 14, "rsi_length": 14},
    {"label": "3,3,6,9",   "k": 3, "d": 3, "length": 9,  "rsi_length": 6},
]

# ── Moving averages ────────────────────────────────────────────────────────────
MA_PERIODS = [50, 100, 200]

# ── Bull Market Support Band (weekly) ─────────────────────────────────────────
BULL_SMA_PERIOD = 20   # 20-week SMA
BULL_EMA_PERIOD = 21   # 21-week EMA

# ── Volume ─────────────────────────────────────────────────────────────────────
VOLUME_MA_PERIOD   = 20
VOLUME_TREND_DAYS  = 5

# ── OBV ────────────────────────────────────────────────────────────────────────
OBV_MA_PERIOD   = 20
OBV_TREND_DAYS  = 20

# ── Keltner Channel ────────────────────────────────────────────────────────────
KC_LENGTH          = 20    # EMA period for basis
KC_ATR_LENGTH      = 10    # ATR period for band width (TradingView default)
KC_SCALAR          = 2.0   # multiplier
KC_WIDTH_SMOOTHING = 10    # SMA period for channel width (widening detection)

# ── Nadaraya-Watson Envelope ───────────────────────────────────────────────────
NW_BANDWIDTH   = 8.0
NW_MULTIPLIER  = 3.0
NW_LOOKBACK    = 500

# ── Signal Classification ───────────────────────────────────────────────────────
# Entry: score must cross ±SIGNAL_ENTRY with slope in the right direction
# Exit:  score must retreat past ±SIGNAL_EXIT to return to Neutral (hysteresis)
# Slope: 5-bar linreg on the SMA(5)-smoothed score (lower = faster but noisier)
SIGNAL_ENTRY      = 30
SIGNAL_EXIT       = 10
SIGNAL_SLOPE_BARS = 5

# ── Color palette (Catppuccin Mocha-inspired) ──────────────────────────────────
C = {
    # Backgrounds
    "bg":      "#1E1E2E",
    "bg2":     "#181825",
    "panel":   "#2A2A3E",
    "border":  "#45475A",

    # Text
    "text":    "#CDD6F4",
    "subtext": "#A6ADC8",

    # Signal colors (cell backgrounds)
    "bull":    "#2D6A4F",   # dark green  → readable with white text
    "bear":    "#7D1E2E",   # dark red
    "neutral": "#2e2e2e",   # dark gray

    # Signal text colors
    "bull_fg": "#A6E3A1",
    "bear_fg": "#F38BA8",
    "neut_fg": "#9ca3af",

    # Chart lines
    "price":   "#CDD6F4",
    "ema50":   "#A855F7",   # purple
    "ema100":  "#67E8F9",   # light blue
    "ema200":  "#FB923C",   # orange
    "sma50":   "#A855F7",   # purple
    "sma100":  "#67E8F9",   # light blue
    "sma200":  "#FB923C",   # orange
    "kc":      "#74C7EC",
    "nw":      "#A6E3A1",
    "bull_sma":"#F9E2AF",
    "bull_ema":"#FAB387",
    "rsi":     "#CBA6F7",
    "rsi_ma":  "#F38BA8",
    "k_line":  "#FAB387",
    "d_line":  "#89B4FA",
    "obv":     "#A6E3A1",
    "obv_ma":  "#FAB387",
    "vol_up":  "#A6E3A1",
    "vol_down":"#F38BA8",
    "vol_ma":  "#F9E2AF",
}
