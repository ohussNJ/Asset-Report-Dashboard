import { useState, useEffect, useRef } from 'react' // useRef kept for Sparkline canvas
import { fetchTickers } from '../api'
import type { Interval, TickerSignal, TickersResponse, SignalState } from '../types'

// ── Helpers ───────────────────────────────────────────────────────────────────

function sigClass(bull: boolean | null | undefined): string {
  if (bull === true)  return 'bull-text'
  if (bull === false) return 'bear-text'
  return 'neut-text'
}

function sigBadgeClass(state: SignalState): string {
  if (state === 'BULL') return 'sig sig-bull'
  if (state === 'BEAR') return 'sig sig-bear'
  return 'sig sig-neutral'
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
  return (
    <span className="ind-score" style={{ background: bg, color: fg }}>{score}</span>
  )
}

function IndRow({
  label, value, bull, score,
}: { label: string; value: string; bull: boolean | null; score?: string }) {
  return (
    <div className="ind-row">
      <span className="ind-label">{label}</span>
      <span className={`ind-value ${sigClass(bull)}`}>{value}</span>
      <IndScore score={score} bull={bull} />
    </div>
  )
}

function MaRow({ label, ma }: { label: string; ma: TickerSignal['EMA'] }) {
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

// ── Sparkline ─────────────────────────────────────────────────────────────────

function Sparkline({ values, state }: { values: number[]; state: SignalState }) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || values.length < 2) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const W = canvas.width
    const H = canvas.height
    const padX = 4, padY = 4
    const w = W - 2 * padX
    const h = H - 2 * padY
    const yMin = -70, rng = 140

    function fy(v: number) {
      return padY + (1 - (v - yMin) / rng) * h
    }

    ctx.clearRect(0, 0, W, H)

    // neutral zone fill
    ctx.fillStyle = 'rgba(60,60,60,0.5)'
    ctx.fillRect(padX, fy(20), w, fy(-20) - fy(20))

    // zero line
    ctx.strokeStyle = '#444'
    ctx.lineWidth = 0.8
    ctx.setLineDash([3, 3])
    ctx.beginPath()
    ctx.moveTo(padX, fy(0))
    ctx.lineTo(padX + w, fy(0))
    ctx.stroke()
    ctx.setLineDash([])

    // score line
    const last = values[values.length - 1]
    const lineColor = state === 'BULL' ? '#4ade80' : state === 'BEAR' ? '#f87171' : '#9ca3af'
    ctx.strokeStyle = lineColor
    ctx.lineWidth = 1.4
    ctx.beginPath()
    values.forEach((v, i) => {
      const x = padX + (i / (values.length - 1)) * w
      const y = fy(v)
      if (i === 0) ctx.moveTo(x, y)
      else ctx.lineTo(x, y)
    })
    ctx.stroke()
    void last
  }, [values, state])

  return (
    <div className="sparkline-wrap">
      <canvas
        ref={canvasRef}
        width={272}
        height={44}
        style={{ display: 'block', width: '100%', height: '100%' }}
      />
    </div>
  )
}

// ── Signal history ────────────────────────────────────────────────────────────

function SignalHistory({ segments }: { segments: TickerSignal['signal_segments'] }) {
  if (!segments || segments.length === 0) return null
  const cur  = segments[segments.length - 1]
  const prev = segments.length >= 2 ? segments[segments.length - 2] : null

  return (
    <div className="sig-history">
      <div className="sig-history-row">
        <span className="sig-history-label">Current:</span>
        <span className={sigBadgeClass(cur.state)}>{cur.state}</span>
        <span className="sig-history-date">{cur.start} – {cur.end}  ({cur.bars}d)</span>
      </div>
      {prev && (
        <div className="sig-history-row">
          <span className="sig-history-label">Previous:</span>
          <span className={sigBadgeClass(prev.state)}>{prev.state}</span>
          <span className="sig-history-date">{prev.start} – {prev.end}  ({prev.bars}d)</span>
        </div>
      )}
    </div>
  )
}

// ── Card ──────────────────────────────────────────────────────────────────────

function Card({ name, s }: { name: string; s: TickerSignal }) {
  const hdrBg = s.overall === true  ? 'var(--bull-bg)'
              : s.overall === false ? 'var(--bear-bg)'
              : 'var(--neut-bg)'
  const hdrFg = s.overall === true  ? 'var(--bull)'
              : s.overall === false ? 'var(--bear)'
              : 'var(--neut)'

  const close = s.close
  const closeStr = close >= 1000 ? `$${(close / 1000).toFixed(2)}k`
                 : close >= 1    ? `$${close.toFixed(2)}`
                 : `$${close.toFixed(4)}`

  const ovr = s.signal === 'BULL' ? 'BULL' : s.signal === 'BEAR' ? 'BEAR' : ''

  const cfg0 = Object.keys(s.StochRSI)[0]
  const cfg1 = Object.keys(s.StochRSI)[1]
  const srsi0 = s.StochRSI[cfg0]
  const srsi1 = s.StochRSI[cfg1]
  const ichi  = s.Ichimoku
  const rsiScore = s.RSI.score
  const rsiBull  = rsiScore ? rsiScore.startsWith('+') ? true : false : null

  return (
    <div className="card">
      <div className="card-header" style={{ background: hdrBg }}>
        <span className="card-name" style={{ color: hdrFg }}>{name}</span>
        {s.pct_change != null && !isNaN(s.pct_change) && (
          <span className={`card-pct ${s.pct_change >= 0 ? 'pct-pos' : 'pct-neg'}`}>
            {s.pct_change >= 0 ? '+' : ''}{s.pct_change.toFixed(1)}%
          </span>
        )}
        <span className="card-close" style={{ color: hdrFg }}>{closeStr}</span>
        <span className="card-score" style={{ color: hdrFg }}>
          {ovr && `${ovr}  `}<ScoreSpan str={s.score_str} />
        </span>
      </div>

      {s.sparkline && s.sparkline.length >= 10 && (
        <Sparkline values={s.sparkline} state={s.signal} />
      )}

      <SignalHistory segments={s.signal_segments} />

      <div className="card-section-hdr">MOMENTUM</div>
      <IndRow label="RSI"           value={s.RSI.text}          bull={rsiBull}           score={rsiScore} />
      <IndRow label="Slow StochRSI" value={srsi0?.text ?? '—'}  bull={srsi0?.bull ?? null} />
      <IndRow label="Fast StochRSI" value={srsi1?.text ?? '—'}  bull={srsi1?.bull ?? null} />

      <div className="card-section-hdr">TREND</div>
      <MaRow label="EMA" ma={s.EMA} />
      <MaRow label="SMA" ma={s.SMA} />

      <div className="card-section-hdr">STRUCTURE</div>
      <IndRow label="Ichi Cloud"  value={ichi.cloud_text}    bull={ichi.cloud_bull}   score={ichi.cloud_score} />
      <IndRow label="Ichi Base"   value={ichi.base_text}     bull={ichi.base_bull}    score={ichi.base_score} />
      <IndRow label="Bull Band"   value={s.BullBand.text}    bull={s.BullBand.bull} />

      <div className="card-section-hdr">VOLUME</div>
      <IndRow label="Volume"      value={s.Volume.text}      bull={s.Volume.bull} />
      <IndRow label="OBV"         value={s.OBV.text}         bull={s.OBV.bull}       score={s.OBV.score} />
      <IndRow label="CNV"         value={s.CNV.text}         bull={s.CNV.bull}       score={s.CNV.score} />

      <div className="card-section-hdr">CHANNELS</div>
      <IndRow label="Keltner"     value={s.Keltner.text}     bull={s.Keltner.bull}   score={s.Keltner.score} />
      <IndRow label="NW Envelope" value={s.NW.text}          bull={s.NW.bull} />
    </div>
  )
}

// ── Summary ───────────────────────────────────────────────────────────────────

export default function Summary({ customTickers = [] }: { customTickers?: string[] }) {
  const [interval, setInterval] = useState<Interval>('1d')
  const [data,     setData]     = useState<TickersResponse | null>(null)
  const [loading,  setLoading]  = useState(true)
  const [error,    setError]    = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    fetchTickers(interval)
      .then(setData)
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false))
  }, [interval, customTickers.length])

  const sorted = data
    ? Object.entries(data).sort(([, a], [, b]) => {
        const na = parseInt(a.score_str) || 0
        const nb = parseInt(b.score_str) || 0
        return nb - na
      })
    : []


  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
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
        <div className="card-grid" style={{ flex: 1, overflowY: 'auto' }}>
          {sorted.map(([name, s]) => (
            <Card key={name} name={name} s={s} />
          ))}
        </div>
      )}
    </div>
  )
}
