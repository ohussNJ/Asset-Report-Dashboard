import type { TickersResponse, WatchlistResponse, IndicatorResponse, MarketData, Interval, Alert, AlertCondition } from './types'

export const TICKER_KEYS = ['SPY', 'GLD', 'NVDA', 'BTC', 'ETH']

export const LOOKBACK_BARS: Record<string, Record<Interval, number>> = {
  '3M':  { '1d': 63,  '1wk': 13 },
  '6M':  { '1d': 126, '1wk': 26 },
  '9M':  { '1d': 189, '1wk': 39 },
  '12M': { '1d': 252, '1wk': 52 },
  '15M': { '1d': 315, '1wk': 65 },
  '18M': { '1d': 378, '1wk': 78 },
}

export const DEFAULT_LOOKBACK: Record<Interval, string> = {
  '1d':  '6M',
  '1wk': '12M',
}

async function get<T>(url: string): Promise<T> {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`${res.status} ${url}`)
  return res.json() as Promise<T>
}

export const fetchTickers    = (iv: Interval) =>
  get<TickersResponse>(`/api/tickers?interval=${iv}`)

export const fetchWatchlist  = (iv: Interval) =>
  get<WatchlistResponse>(`/api/watchlist?interval=${iv}`)

export const fetchIndicators = (sym: string, iv: Interval) =>
  get<IndicatorResponse>(`/api/tickers/${sym}/indicators?interval=${iv}`)

export const fetchMarket = () =>
  get<MarketData>('/api/market')

export const fetchWatchlistCategories = () =>
  get<string[]>('/api/watchlist/categories')

export async function addCustomTicker(symbol: string): Promise<void> {
  const res = await fetch(`/api/custom-ticker/${encodeURIComponent(symbol)}`, { method: 'POST' })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error((err as { detail?: string }).detail ?? `${res.status}`)
  }
}

export const fetchAlerts = () =>
  get<Alert[]>('/api/alerts')

export async function createAlert(symbol: string, condition_type: AlertCondition, threshold: number | null): Promise<Alert> {
  const res = await fetch('/api/alerts', {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ symbol, condition_type, threshold }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error((err as { detail?: string }).detail ?? `${res.status}`)
  }
  return res.json() as Promise<Alert>
}

export async function deleteAlert(id: number): Promise<void> {
  const res = await fetch(`/api/alerts/${id}`, { method: 'DELETE' })
  if (!res.ok && res.status !== 404) throw new Error(`${res.status}`)
}

export async function addWatchlistItem(symbol: string, name: string, category: string): Promise<void> {
  const res = await fetch('/api/watchlist/add', {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ symbol, name, category }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error((err as { detail?: string }).detail ?? `${res.status}`)
  }
}

