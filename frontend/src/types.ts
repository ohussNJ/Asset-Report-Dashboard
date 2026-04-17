export interface MaPeriod {
  value?: number
  above?: boolean | null
}

export type MaIndicator = {
  score50?:  string
  score200?: string
  text?: string
  bull?: boolean | null
} & Record<number, MaPeriod | undefined>

export type Interval = '1d' | '1wk'
export type Lookback = '3M' | '6M' | '9M' | '12M' | '15M' | '18M'
export type SignalState = 'BULL' | 'BEAR' | 'NEUTRAL'

export interface SignalSegment {
  state: SignalState
  start: string
  end: string
  bars: number
}

export interface TickerSignal {
  signal: SignalState
  score_str: string
  slope: number
  bars_held: number
  close: number
  pct_change: number
  overall: boolean | null
  sparkline: number[]
  signal_segments: SignalSegment[]
  RSI: {
    value: number
    text: string
    bull: boolean | null
    score: string
  }
  StochRSI: Record<string, {
    K: number
    D: number
    text: string
    bull: boolean | null
  }>
  EMA: MaIndicator
  SMA: MaIndicator
  BullBand: { text: string; bull: boolean | null; sma: number; ema: number }
  Ichimoku: { cloud_text: string; base_text: string; cloud_bull: boolean | null; base_bull: boolean | null; cloud_score?: string; base_score?: string }
  Volume: { text: string; bull: boolean | null }
  OBV: { text: string; bull: boolean | null; score?: string }
  CNV: { text: string; bull: boolean | null; score?: string }
  Keltner: { text: string; bull: boolean | null; score?: string }
  NW: { text: string; bull: boolean | null }
}

export type TickersResponse = Record<string, TickerSignal>

export interface WatchlistEntry extends TickerSignal {
  symbol: string
  name: string
}

export type WatchlistResponse = Record<string, WatchlistEntry[]>

export interface OHLCVPoint {
  time: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export interface LinePoint {
  time: string
  value: number
}

export interface DivergenceLine {
  type: 'bullish' | 'bearish'
  price_t1: string
  price_t2: string
  price_v1: number
  price_v2: number
  ind_t1: string
  ind_t2: string
  ind_v1: number
  ind_v2: number
}

export interface IndicatorResponse {
  candles: OHLCVPoint[]
  ema50: LinePoint[]
  ema100: LinePoint[]
  ema200: LinePoint[]
  sma50: LinePoint[]
  sma100: LinePoint[]
  sma200: LinePoint[]
  kc_upper: LinePoint[]
  kc_basis: LinePoint[]
  kc_lower: LinePoint[]
  nw: LinePoint[]
  nw_upper: LinePoint[]
  nw_lower: LinePoint[]
  bull_sma: LinePoint[]
  bull_ema: LinePoint[]
  rsi: LinePoint[]
  rsi_ma: LinePoint[]
  obv: LinePoint[]
  obv_ma: LinePoint[]
  vol_ma: LinePoint[]
  score: LinePoint[]
  srsi_k_0: LinePoint[]
  srsi_d_0: LinePoint[]
  srsi_k_1: LinePoint[]
  srsi_d_1: LinePoint[]
  cnv: LinePoint[]
  price_17: number | null
  price_42: number | null
  div_rsi: DivergenceLine[]
  div_obv: DivergenceLine[]
  div_score: DivergenceLine[]
}

export interface MarketData {
  vix: number | null
  move: number | null
  move_slope: number | null
}

export type AlertCondition = 'price_above' | 'price_below' | 'signal_bull' | 'signal_bear'

export interface Alert {
  id: number
  symbol: string
  condition_type: AlertCondition
  threshold: number | null
  triggered: boolean
  created_at: string
  triggered_at: string | null
}
