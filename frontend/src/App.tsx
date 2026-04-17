import { useState, useEffect, useRef } from 'react'
import Summary   from './components/Summary'
import Watchlist from './components/Watchlist'
import Charts    from './components/Charts'
import Info      from './components/Info'
import AlertsTab from './components/Alerts'
import { fetchMarket, addCustomTicker, fetchAlerts, createAlert, deleteAlert } from './api'
import type { MarketData, Alert, AlertCondition } from './types'

const TABS = ['SUMMARY', 'WATCHLIST', 'CHARTS', 'ALERTS', 'INFO'] as const
type Tab = typeof TABS[number]

export default function App() {
  const [tab, setTab]             = useState<Tab>('SUMMARY')
  const [market, setMarket]       = useState<MarketData | null>(null)
  const [customTickers, setCustomTickers] = useState<string[]>([])
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [addingTicker, setAddingTicker]   = useState(false)
  const [tickerInput,  setTickerInput]    = useState('')
  const [tickerErr,    setTickerErr]      = useState<string | null>(null)
  const [tickerBusy,   setTickerBusy]     = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    fetchMarket().then(setMarket).catch(() => null)
    fetchAlerts().then(setAlerts).catch(() => null)

    if ('Notification' in window && Notification.permission === 'default') {
      Notification.requestPermission()
    }

    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${proto}://${window.location.host}/ws/status`)
    ws.onmessage = (e: MessageEvent) => {
      if (e.data === 'refresh') {
        fetchMarket().then(setMarket).catch(() => null)
      } else if (typeof e.data === 'string' && e.data.startsWith('alert:')) {
        try {
          const alert: Alert = JSON.parse(e.data.slice(6))
          setAlerts(prev => prev.map(a => a.id === alert.id ? alert : a))
          if (Notification.permission === 'granted') {
            const cond = alert.condition_type.replace('_', ' ')
            const detail = alert.threshold != null ? ` @ $${alert.threshold}` : ''
            new Notification(`Alert triggered: ${alert.symbol}`, {
              body: `${cond}${detail}`,
            })
          }
        } catch { /* ignore malformed */ }
      }
    }
    return () => ws.close()
  }, [])

  useEffect(() => {
    if (addingTicker) inputRef.current?.focus()
  }, [addingTicker])

  async function handleAddTicker(e: React.FormEvent) {
    e.preventDefault()
    const sym = tickerInput.trim().toUpperCase()
    if (!sym) return
    setTickerBusy(true); setTickerErr(null)
    try {
      await addCustomTicker(sym)
      setCustomTickers(prev => prev.includes(sym) ? prev : [...prev, sym])
      setTickerInput(''); setAddingTicker(false)
    } catch (ex) {
      setTickerErr(String(ex))
    } finally {
      setTickerBusy(false)
    }
  }

  async function handleAddAlert(symbol: string, condition_type: AlertCondition, threshold: number | null) {
    const created = await createAlert(symbol, condition_type, threshold)
    setAlerts(prev => [...prev, created])
  }

  async function handleRemoveAlert(id: number) {
    await deleteAlert(id).catch(() => null)
    setAlerts(prev => prev.filter(x => x.id !== id))
  }

  function vixColor(v: number | null): string {
    if (v == null) return 'var(--text)'
    if (v >= 20) return 'var(--bear)'
    if (v < 15)  return 'var(--bull)'
    return 'var(--amber)'
  }

  function moveColor(slope: number | null): string {
    if (slope == null) return 'var(--text)'
    if (slope > 0) return 'var(--bear)'
    if (slope < 0) return 'var(--bull)'
    return 'var(--text)'
  }

  return (
    <div className="app">
      <header className="header">
        <span className="header-title">ASSET REPORT</span>
        <nav className="tab-bar">
          {TABS.map(t => (
            <button
              key={t}
              className={`tab-btn${tab === t ? ' active' : ''}`}
              onClick={() => setTab(t)}
            >
              {t}
            </button>
          ))}
          <div className="tab-add-ticker">
            {addingTicker ? (
              <form className="tab-add-form" onSubmit={handleAddTicker}>
                <input
                  ref={inputRef}
                  className="tab-add-input"
                  placeholder="Symbol…"
                  value={tickerInput}
                  onChange={e => { setTickerInput(e.target.value.toUpperCase()); setTickerErr(null) }}
                />
                {tickerErr && <span className="tab-add-err">{tickerErr}</span>}
                <button className="tab-btn" type="submit" disabled={tickerBusy}>
                  {tickerBusy ? '…' : 'ADD'}
                </button>
                <button className="tab-btn" type="button" onClick={() => { setAddingTicker(false); setTickerInput(''); setTickerErr(null) }}>✕</button>
              </form>
            ) : (
              <button className="tab-btn" onClick={() => setAddingTicker(true)}>＋ Ticker</button>
            )}
          </div>
        </nav>
        <div className="header-market">
          {market?.vix != null && (
            <div className="market-item">
              <span className="market-label">VIX</span>
              <span className="market-value" style={{ color: vixColor(market.vix) }}>
                {market.vix.toFixed(1)}
              </span>
            </div>
          )}
          {market?.move != null && (
            <div className="market-item">
              <span className="market-label">MOVE</span>
              <span className="market-value" style={{ color: moveColor(market.move_slope) }}>
                {Math.round(market.move)}
              </span>
            </div>
          )}
        </div>
      </header>
      <main className="main">
        <div style={{ display: tab === 'SUMMARY'   ? 'block' : 'none' }}><Summary   customTickers={customTickers} /></div>
        <div style={{ display: tab === 'WATCHLIST' ? 'block' : 'none' }}><Watchlist customTickers={customTickers} onAddTicker={async (sym) => { await addCustomTicker(sym); setCustomTickers(prev => prev.includes(sym) ? prev : [...prev, sym]) }} /></div>
        <div style={{ display: tab === 'CHARTS'    ? 'block' : 'none' }}><Charts    customTickers={customTickers} /></div>
        <div style={{ display: tab === 'ALERTS'    ? 'block' : 'none' }}><AlertsTab alerts={alerts} onAdd={handleAddAlert} onRemove={handleRemoveAlert} /></div>
        <div style={{ display: tab === 'INFO'      ? 'block' : 'none' }}><Info /></div>
      </main>
    </div>
  )
}
