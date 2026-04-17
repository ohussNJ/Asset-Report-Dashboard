import { useState, useEffect } from 'react'
import { fetchWatchlist } from '../api'
import type { Interval, WatchlistEntry, WatchlistResponse, SignalState } from '../types'

// ── Shared helpers (mirrors Summary.tsx) ──────────────────────────────────────

function sigBadgeClass(state: SignalState) {
  if (state === 'BULL') return 'sig sig-bull'
  if (state === 'BEAR') return 'sig sig-bear'
  return 'sig sig-neutral'
}

function sigClass(bull: boolean | null | undefined) {
  if (bull === true)  return 'bull-text'
  if (bull === false) return 'bear-text'
  return 'neut-text'
}

function ScoreSpan({ str }: { str: string }) {
  if (!str || str === '0') return <span className="score-zero">0</span>
  if (str.startsWith('+')) return <span className="score-pos">{str}</span>
  return <span className="score-neg">{str}</span>
}

function IndScore({ score, bull }: { score?: string; bull: boolean | null }) {
  if (!score) return null
  const bg = bull === true ? '#1a2e1a' : bull === false ? '#2e1a1a' : '#2a2614'
  const fg = bull === true ? 'var(--bull)' : bull === false ? 'var(--bear)' : '#aaa'
  return <span className="ind-score" style={{ background: bg, color: fg }}>{score}</span>
}

function IndRow({ label, value, bull, score }: { label: string; value: string; bull: boolean | null; score?: string }) {
  return (
    <div className="ind-row">
      <span className="ind-label">{label}</span>
      <span className={`ind-value ${sigClass(bull)}`}>{value}</span>
      <IndScore score={score} bull={bull} />
    </div>
  )
}

function MaRow({ label, ma }: { label: string; ma: WatchlistEntry['EMA'] }) {
  const periods = [50, 100, 200]
  const total = (+(ma['score50'] ?? '0').replace('+', '') || 0) +
                (+(ma['score200'] ?? '0').replace('+', '') || 0)
  const sc = total !== 0 ? (total > 0 ? `+${total}` : String(total)) : undefined
  return (
    <div className="ind-row">
      <span className="ind-label">{label}</span>
      <span className="ind-value" style={{ display: 'flex', gap: 8 }}>
        {periods.map(p => {
          const above = (ma[p] as { above?: boolean | null })?.above
          return (
            <span key={p} className={sigClass(above)}>
              {p}{above === true ? '↑' : above === false ? '↓' : '?'}
            </span>
          )
        })}
      </span>
      {sc && <IndScore score={sc} bull={total > 0} />}
    </div>
  )
}

// ── Expanded detail card ──────────────────────────────────────────────────────

function DetailCard({ s }: { s: WatchlistEntry }) {
  const cfg0 = Object.keys(s.StochRSI)[0]
  const cfg1 = Object.keys(s.StochRSI)[1]
  const srsi0 = s.StochRSI[cfg0]
  const srsi1 = s.StochRSI[cfg1]
  const ichi  = s.Ichimoku
  const rsiScore = s.RSI?.score
  const rsiBull  = rsiScore ? rsiScore.startsWith('+') ? true : false : null

  return (
    <div style={{ padding: '6px 0' }}>
      <div className="card-section-hdr">MOMENTUM</div>
      <IndRow label="RSI"           value={s.RSI.text}          bull={rsiBull}            score={rsiScore} />
      <IndRow label="Slow StochRSI" value={srsi0?.text ?? '—'}  bull={srsi0?.bull ?? null} />
      <IndRow label="Fast StochRSI" value={srsi1?.text ?? '—'}  bull={srsi1?.bull ?? null} />

      <div className="card-section-hdr">TREND</div>
      <MaRow label="EMA" ma={s.EMA} />
      <MaRow label="SMA" ma={s.SMA} />

      <div className="card-section-hdr">STRUCTURE</div>
      <IndRow label="Ichi Cloud"  value={ichi.cloud_text}  bull={ichi.cloud_bull}  score={ichi.cloud_score} />
      <IndRow label="Ichi Base"   value={ichi.base_text}   bull={ichi.base_bull}   score={ichi.base_score} />
      <IndRow label="Bull Band"   value={s.BullBand.text}  bull={s.BullBand.bull} />

      <div className="card-section-hdr">VOLUME</div>
      <IndRow label="Volume"      value={s.Volume.text}    bull={s.Volume.bull} />
      <IndRow label="OBV"         value={s.OBV.text}       bull={s.OBV.bull}       score={s.OBV.score} />
      <IndRow label="CNV"         value={s.CNV.text}       bull={s.CNV.bull}       score={s.CNV.score} />

      <div className="card-section-hdr">CHANNELS</div>
      <IndRow label="Keltner"     value={s.Keltner.text}   bull={s.Keltner.bull}   score={s.Keltner.score} />
      <IndRow label="NW Envelope" value={s.NW.text}        bull={s.NW.bull} />
    </div>
  )
}

// ── Row ───────────────────────────────────────────────────────────────────────

function WlRow({ e, isAdded, onAdd }: { e: WatchlistEntry; isAdded: boolean; onAdd: (sym: string) => void }) {
  const [open, setOpen] = useState(false)

  const close = e.close
  const closeStr = close >= 1000 ? `$${(close / 1000).toFixed(2)}k`
                 : close >= 1    ? `$${close.toFixed(2)}`
                 : `$${close.toFixed(4)}`

  const segs    = e.signal_segments ?? []
  const cur     = segs[segs.length - 1]
  const prev    = segs.length >= 2 ? segs[segs.length - 2] : null

  return (
    <div>
      <div className="wl-row">
        <span className="wl-sym">{e.symbol}</span>
        <span className="wl-name">{e.name}</span>

        <div className="wl-sig-history">
          {cur && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 10 }}>
              <span style={{ color: 'var(--text-dim)', width: 48, flexShrink: 0 }}>Current:</span>
              <span className={sigBadgeClass(cur.state)}>{cur.state}</span>
              <span style={{ color: 'var(--text-dim)' }}>{cur.start} – {cur.end}  ({cur.bars}d)</span>
            </div>
          )}
          {prev && (
            <span style={{ color: 'var(--border-hi)', fontSize: 10, padding: '0 6px' }}>|</span>
          )}
          {prev && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 10 }}>
              <span style={{ color: 'var(--text-dim)', width: 52, flexShrink: 0 }}>Previous:</span>
              <span className={sigBadgeClass(prev.state)}>{prev.state}</span>
              <span style={{ color: 'var(--text-dim)' }}>{prev.start} – {prev.end}  ({prev.bars}d)</span>
            </div>
          )}
        </div>

        <div className="wl-price-group">
          <span className="wl-price">{closeStr}</span>
          <span className={`wl-pct ${e.pct_change >= 0 ? 'pct-pos' : 'pct-neg'}`}>
            {e.pct_change >= 0 ? '+' : ''}{e.pct_change?.toFixed(2)}%
          </span>
          <span
            className="ind-score"
            style={{
              background: e.overall === true ? '#1a2e1a' : e.overall === false ? '#2e1a1a' : 'var(--neut-bg)',
              color:      e.overall === true ? 'var(--bull)' : e.overall === false ? 'var(--bear)' : 'var(--neut)',
              minWidth: 40,
              textAlign: 'center',
            }}
          >
            <ScoreSpan str={e.score_str} />
          </span>
          <button
            className={`wl-add-ticker-btn${isAdded ? ' added' : ''}`}
            disabled={isAdded}
            onClick={() => !isAdded && onAdd(e.symbol)}
          >
            {isAdded ? 'Added' : '＋ Add'}
          </button>
          <button className="wl-expand-btn" onClick={() => setOpen(o => !o)}>
            {open ? '▲' : '▼'}
          </button>
        </div>
      </div>

      {open && (
        <div className="wl-detail">
          <DetailCard s={e} />
        </div>
      )}
    </div>
  )
}

// ── Watchlist ─────────────────────────────────────────────────────────────────

export default function Watchlist({ customTickers = [], onAddTicker }: { customTickers?: string[]; onAddTicker?: (sym: string) => void }) {
  const [interval, setInterval] = useState<Interval>('1d')
  const [data,     setData]     = useState<WatchlistResponse | null>(null)
  const [loading,  setLoading]  = useState(true)
  const [error,    setError]    = useState<string | null>(null)

  function load() {
    setLoading(true)
    setError(null)
    fetchWatchlist(interval)
      .then(setData)
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [interval])

  return (
    <div>
      <div className="controls">
        <div className="ctrl-group">
          <span className="ctrl-label">INTERVAL</span>
          {(['1d', '1wk'] as Interval[]).map(iv => (
            <button
              key={iv}
              className={`seg-btn${interval === iv ? ' active' : ''}`}
              onClick={() => setInterval(iv)}
            >
              {iv === '1d' ? 'DAILY' : 'WEEKLY'}
            </button>
          ))}
        </div>
      </div>

      {loading && <div className="status">loading...</div>}
      {error   && <div className="status">error: {error}</div>}

      {data && (
        <div className="wl-content">
          {Object.entries(data).map(([category, entries]) => (
            <div key={category}>
              <div className="wl-category">{category.toUpperCase()}</div>
              {[...entries]
                .sort((a, b) => (parseInt(b.score_str) || 0) - (parseInt(a.score_str) || 0))
                .map(e => (
                  <WlRow
                    key={e.symbol}
                    e={e}
                    isAdded={customTickers.includes(e.symbol)}
                    onAdd={sym => onAddTicker?.(sym)}
                  />
                ))
              }
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
