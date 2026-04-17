import { useState, useRef, useEffect } from 'react'
import type { Alert, AlertCondition } from '../types'

const CONDITION_LABELS: Record<AlertCondition, string> = {
  price_above: 'Price Above',
  price_below: 'Price Below',
  signal_bull: 'Signal → Bull',
  signal_bear: 'Signal → Bear',
}

const PRICE_CONDITIONS = new Set<AlertCondition>(['price_above', 'price_below'])

function conditionLabel(c: AlertCondition, threshold: number | null): string {
  const base = CONDITION_LABELS[c]
  if (PRICE_CONDITIONS.has(c) && threshold != null) {
    const fmt = threshold >= 1 ? threshold.toFixed(2) : threshold.toFixed(4)
    return `${base}  $${fmt}`
  }
  return base
}

function formatDate(iso: string): string {
  if (!iso) return '—'
  return iso.slice(0, 10)
}

// ── Add form ──────────────────────────────────────────────────────────────────

function AddForm({ onAdd }: { onAdd: (symbol: string, condition: AlertCondition, threshold: number | null) => Promise<void> }) {
  const [open,      setOpen]      = useState(false)
  const [symbol,    setSymbol]    = useState('')
  const [condition, setCondition] = useState<AlertCondition>('price_above')
  const [threshold, setThreshold] = useState('')
  const [busy,      setBusy]      = useState(false)
  const [err,       setErr]       = useState<string | null>(null)
  const symRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (open) setTimeout(() => symRef.current?.focus(), 0)
  }, [open])

  const needsThreshold = PRICE_CONDITIONS.has(condition)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    const sym = symbol.trim().toUpperCase()
    if (!sym) return
    if (needsThreshold) {
      const t = parseFloat(threshold)
      if (isNaN(t) || t <= 0) { setErr('Enter a valid price'); return }
    }
    setBusy(true); setErr(null)
    try {
      await onAdd(sym, condition, needsThreshold ? parseFloat(threshold) : null)
      setSymbol(''); setThreshold(''); setOpen(false)
    } catch (ex) {
      setErr(String(ex))
    } finally {
      setBusy(false)
    }
  }

  if (!open) {
    return (
      <button className="alerts-add-btn" onClick={() => setOpen(true)}>＋ Add Alert</button>
    )
  }

  return (
    <form className="alerts-add-form" onSubmit={submit}>
      <input
        ref={symRef}
        className="alerts-input alerts-input-sym"
        placeholder="Symbol"
        value={symbol}
        onChange={e => { setSymbol(e.target.value.toUpperCase()); setErr(null) }}
      />
      <select
        className="alerts-select"
        value={condition}
        onChange={e => { setCondition(e.target.value as AlertCondition); setErr(null) }}
      >
        {(Object.keys(CONDITION_LABELS) as AlertCondition[]).map(c => (
          <option key={c} value={c}>{CONDITION_LABELS[c]}</option>
        ))}
      </select>
      {needsThreshold && (
        <input
          className="alerts-input alerts-input-price"
          type="number"
          step="any"
          placeholder="Price"
          value={threshold}
          onChange={e => { setThreshold(e.target.value); setErr(null) }}
          onKeyDown={e => e.key === 'Escape' && setOpen(false)}
        />
      )}
      {err && <span className="alerts-err">{err}</span>}
      <button className="alerts-submit-btn" type="submit" disabled={busy}>
        {busy ? '…' : 'ADD'}
      </button>
      <button className="alerts-cancel-btn" type="button" onClick={() => { setOpen(false); setErr(null) }}>✕</button>
    </form>
  )
}

// ── Alerts list ───────────────────────────────────────────────────────────────

export default function Alerts({
  alerts,
  onAdd,
  onRemove,
}: {
  alerts: Alert[]
  onAdd: (symbol: string, condition: AlertCondition, threshold: number | null) => Promise<void>
  onRemove: (id: number) => void
}) {
  const active    = alerts.filter(a => !a.triggered)
  const triggered = alerts.filter(a => a.triggered)

  function renderRow(a: Alert) {
    return (
      <div key={a.id} className={`alerts-row${a.triggered ? ' alerts-row-triggered' : ''}`}>
        <span className="alerts-col-sym">{a.symbol}</span>
        <span className="alerts-col-cond">{conditionLabel(a.condition_type, a.threshold)}</span>
        <span className="alerts-col-status">
          {a.triggered
            ? <span className="alerts-status-triggered">TRIGGERED  {formatDate(a.triggered_at ?? '')}</span>
            : <span className="alerts-status-active">ACTIVE</span>}
        </span>
        <span className="alerts-col-created">{formatDate(a.created_at)}</span>
        <button className="alerts-delete-btn" onClick={() => onRemove(a.id)}>✕</button>
      </div>
    )
  }

  return (
    <div className="alerts-wrap">
      <div className="alerts-toolbar">
        <AddForm onAdd={onAdd} />
      </div>

      {alerts.length === 0 ? (
        <div className="status">No alerts set.</div>
      ) : (
        <>
          <div className="alerts-table-hdr">
            <span className="alerts-col-sym">SYMBOL</span>
            <span className="alerts-col-cond">CONDITION</span>
            <span className="alerts-col-status">STATUS</span>
            <span className="alerts-col-created">CREATED</span>
            <span style={{ width: 24 }} />
          </div>

          {active.length > 0 && active.map(renderRow)}

          {triggered.length > 0 && (
            <>
              <div className="alerts-section-hdr">TRIGGERED</div>
              {triggered.map(renderRow)}
            </>
          )}
        </>
      )}
    </div>
  )
}
