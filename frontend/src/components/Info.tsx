const SECTIONS = [
  {
    name: 'MOMENTUM',
    rows: [
      {
        ind: 'RSI',
        params: 'Period: 14  ·  MA: SMA 14',
        bull: 'Slope > 0 AND RSI > MA  (+10)\nRSI ≥ 56  (+10)',
        bear: 'Slope ≤ 0 AND RSI < MA  (+10)\nRSI ≤ 36  (+10)',
      },
      {
        ind: 'Slow StochRSI',
        params: 'K: 3  D: 3  Stoch: 14  RSI: 14',
        bull: 'K > D',
        bear: 'K ≤ D',
      },
      {
        ind: 'Fast StochRSI',
        params: 'K: 3  D: 3  Stoch: 9   RSI: 6',
        bull: 'K > D',
        bear: 'K ≤ D',
      },
    ],
  },
  {
    name: 'TREND',
    rows: [
      {
        ind: 'EMA  50/100/200',
        params: 'Periods: 50, 100, 200',
        bull: 'Price above ALL three EMAs',
        bear: 'Price below ALL three EMAs',
      },
      {
        ind: 'SMA  50/100/200',
        params: 'Periods: 50, 100, 200',
        bull: 'Price above ALL three SMAs',
        bear: 'Price below ALL three SMAs',
      },
    ],
  },
  {
    name: 'STRUCTURE',
    rows: [
      {
        ind: 'Bull Market Band',
        params: '20w SMA  ·  21w EMA',
        bull: 'Price above both bands',
        bear: 'Price below both bands',
      },
      {
        ind: 'Ichimoku Cloud',
        params: 'Conv: 9  Base: 26  SpanB: 52',
        bull: 'Price above cloud top',
        bear: 'Price below cloud bottom',
      },
      {
        ind: 'Ichimoku Base',
        params: 'Base Length: 26',
        bull: 'Price above base line',
        bear: 'Price below base line',
      },
    ],
  },
  {
    name: 'VOLUME',
    rows: [
      {
        ind: 'Volume',
        params: 'MA: 20  Trend: 5 bars',
        bull: 'Vol above MA AND slope > 0',
        bear: 'Vol below MA AND slope ≤ 0',
      },
      {
        ind: 'OBV',
        params: 'EMA: 20  Trend: 20 bars',
        bull: 'OBV > EMA AND slope > 0',
        bear: 'OBV < EMA AND slope ≤ 0',
      },
      {
        ind: 'CNV',
        params: 'SMA: 20',
        bull: 'CNV > SMA',
        bear: 'CNV ≤ SMA',
      },
    ],
  },
  {
    name: 'CHANNELS',
    rows: [
      {
        ind: 'Keltner Channel',
        params: 'EMA: 20  ATR: 10  Scalar: 2',
        bull: 'Price > upper AND widening',
        bear: 'Price < lower AND widening',
      },
      {
        ind: 'NW Envelope',
        params: 'BW: 8  Mult: 3  Lookback: 500',
        bull: 'NW lower band inside Keltner',
        bear: 'NW upper band inside Keltner',
      },
    ],
  },
]

const SIG_ROWS = [
  {
    label: 'BULL',
    cls: 'sig sig-bull',
    entry: 'Smoothed score crosses above +30  AND  5-bar slope is positive (score improving)',
    exit:  'Smoothed score retreats below +10',
  },
  {
    label: 'BEAR',
    cls: 'sig sig-bear',
    entry: 'Smoothed score crosses below −30  AND  5-bar slope is negative (score deteriorating)',
    exit:  'Smoothed score recovers above −10',
  },
  {
    label: 'NEUTRAL',
    cls: 'sig sig-neutral',
    entry: 'Neither BULL nor BEAR entry condition is met',
    exit:  'N/A — default state',
  },
]

export default function Info() {
  return (
    <div className="info-content">

      {/* Indicator table header */}
      <div className="info-hdr-row">
        <span className="info-col-ind  info-col-hdr">Indicator</span>
        <span className="info-col-params info-col-hdr">Parameters</span>
        <span className="info-col-bull  info-col-hdr">Bull</span>
        <span className="info-col-bear  info-col-hdr">Bear</span>
      </div>

      {SECTIONS.map(sec => (
        <div key={sec.name}>
          <div className="info-section-hdr">{sec.name}</div>
          {sec.rows.map((r, i) => (
            <div key={r.ind} className="info-row" style={{ background: i % 2 === 0 ? 'var(--card)' : 'var(--bg)' }}>
              <span className="info-col-ind">{r.ind}</span>
              <span className="info-col-params">{r.params}</span>
              <span className="info-col-bull" style={{ whiteSpace: 'pre-line' }}>{r.bull}</span>
              <span className="info-col-bear" style={{ whiteSpace: 'pre-line' }}>{r.bear}</span>
            </div>
          ))}
        </div>
      ))}

      {/* Signal classification */}
      <div className="info-section-hdr" style={{ marginTop: 16 }}>SIGNAL CLASSIFICATION</div>

      <div className="info-hdr-row sig-class-table">
        <span className="sig-class-col-sig  info-col-hdr">Signal</span>
        <span className="sig-class-col-entry info-col-hdr">Entry condition</span>
        <span className="sig-class-col-exit  info-col-hdr">Exits to Neutral when</span>
      </div>

      {SIG_ROWS.map((r, i) => (
        <div key={r.label} className="sig-class-row" style={{ background: i % 2 === 0 ? 'var(--card)' : 'var(--bg)' }}>
          <span className="sig-class-col-sig">
            <span className={r.cls}>{r.label}</span>
          </span>
          <span className="sig-class-col-entry">{r.entry}</span>
          <span className="sig-class-col-exit">{r.exit}</span>
        </div>
      ))}

    </div>
  )
}
