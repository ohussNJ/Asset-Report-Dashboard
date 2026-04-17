import { useState, useEffect, useRef, useCallback } from 'react'
import {
  createChart,
  ColorType,
  CrosshairMode,
  LineStyle,
  type IChartApi,
  type ISeriesApi,
  type CandlestickSeriesOptions,
  type LineSeriesOptions,
} from 'lightweight-charts'
import { fetchIndicators } from '../api'
import { TICKER_KEYS, LOOKBACK_BARS, DEFAULT_LOOKBACK } from '../api'
import type { Interval, IndicatorResponse, OHLCVPoint, LinePoint, DivergenceLine } from '../types'

// ── Chart theme ───────────────────────────────────────────────────────────────

const T = {
  bg:     '#0f0f0f',
  grid:   '#1a1a1a',
  border: '#222',
  muted:  '#555',
}

const C = {
  ema50:   '#a855f7',
  ema100:  '#67e8f9',
  ema200:  '#fb923c',
  sma50:   '#a855f7',
  sma100:  '#67e8f9',
  sma200:  '#fb923c',
  kc:      '#74c7ec',
  nw:      '#a6e3a1',
  bullSma: '#f9e2af',
  bullEma: '#fab387',
  rsi:     '#cba6f7',
  rsiMa:   '#f38ba8',
  kLine:   '#fab387',
  dLine:   '#89b4fa',
  obv:     '#a6e3a1',
  obvMa:   '#fab387',
  volUp:   '#4ade80',
  volDown: '#f87171',
  volMa:   '#f9e2af',
  score:   '#fbbf24',
  cnvBull: '#3b82f6',
  cnvBear: '#ef4444',
}

function chartOpts(width: number, height: number) {
  return {
    layout: {
      background: { type: ColorType.Solid, color: T.bg },
      textColor: T.muted,
    },
    grid: {
      vertLines: { color: T.grid },
      horzLines: { color: T.grid },
    },
    crosshair: { mode: CrosshairMode.Normal },
    rightPriceScale: { borderColor: T.border },
    timeScale: { borderColor: T.border, timeVisible: true },
    width,
    height,
  }
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function sliceCandles(candles: OHLCVPoint[], n: number): OHLCVPoint[] {
  return n > 0 ? candles.slice(-n) : candles
}

function sliceLine(pts: LinePoint[], n: number): LinePoint[] {
  return n > 0 ? pts.slice(-n) : pts
}

function addLine(
  chart: IChartApi,
  data: LinePoint[],
  opts: Partial<LineSeriesOptions>,
): ISeriesApi<'Line'> {
  const s = chart.addLineSeries({ priceLineVisible: false, lastValueVisible: false, ...opts })
  s.setData(data)
  return s
}

function addDivergenceLines(
  chart: IChartApi,
  divs: DivergenceLine[],
  usePrice: boolean,
) {
  for (const d of divs) {
    const color = d.type === 'bullish' ? '#4ade80' : '#f87171'
    const t1 = usePrice ? d.price_t1 : d.ind_t1
    const t2 = usePrice ? d.price_t2 : d.ind_t2
    const v1 = usePrice ? d.price_v1 : d.ind_v1
    const v2 = usePrice ? d.price_v2 : d.ind_v2
    const s = chart.addLineSeries({
      color,
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      priceLineVisible: false,
      lastValueVisible: false,
    })
    s.setData([{ time: t1 as import('lightweight-charts').Time, value: v1 }, { time: t2 as import('lightweight-charts').Time, value: v2 }])
  }
}

function addPricePanel(chart: IChartApi, data: IndicatorResponse, n: number) {
  const candles = sliceCandles(data.candles, n)

  const cs = chart.addCandlestickSeries({
    upColor:        '#4ade80',
    downColor:      '#f87171',
    borderUpColor:  '#4ade80',
    borderDownColor:'#f87171',
    wickUpColor:    '#4ade80',
    wickDownColor:  '#f87171',
  } as Partial<CandlestickSeriesOptions>)
  cs.setData(candles)

  if (data.bull_sma?.length) {
    addLine(chart, sliceLine(data.bull_sma, n), { color: C.bullSma, lineWidth: 1, lineStyle: LineStyle.Dotted })
  }
  if (data.bull_ema?.length) {
    addLine(chart, sliceLine(data.bull_ema, n), { color: C.bullEma, lineWidth: 1, lineStyle: LineStyle.Dotted })
  }
  if (data.ema50?.length)  addLine(chart, sliceLine(data.ema50,  n), { color: C.ema50,  lineWidth: 1 })
  if (data.ema100?.length) addLine(chart, sliceLine(data.ema100, n), { color: C.ema100, lineWidth: 1 })
  if (data.ema200?.length) addLine(chart, sliceLine(data.ema200, n), { color: C.ema200, lineWidth: 1 })
  if (data.sma50?.length)  addLine(chart, sliceLine(data.sma50,  n), { color: C.sma50,  lineWidth: 1, lineStyle: LineStyle.Dashed })
  if (data.sma100?.length) addLine(chart, sliceLine(data.sma100, n), { color: C.sma100, lineWidth: 1, lineStyle: LineStyle.Dashed })
  if (data.sma200?.length) addLine(chart, sliceLine(data.sma200, n), { color: C.sma200, lineWidth: 1, lineStyle: LineStyle.Dashed })
}

function syncCharts(charts: IChartApi[]) {
  let syncing = false
  for (const c of charts) {
    c.timeScale().subscribeVisibleLogicalRangeChange(range => {
      if (syncing || !range) return
      syncing = true
      for (const other of charts) {
        if (other !== c) other.timeScale().setVisibleLogicalRange(range)
      }
      syncing = false
    })
  }
}

function useResizeObserver(
  refs: React.RefObject<HTMLDivElement>[],
  charts: React.MutableRefObject<(IChartApi | null)[]>,
) {
  useEffect(() => {
    const ro = new ResizeObserver(() => {
      refs.forEach((ref, i) => {
        if (ref.current && charts.current[i]) {
          charts.current[i]!.applyOptions({ width: ref.current.clientWidth })
          charts.current[i]!.timeScale().fitContent()
        }
      })
    })
    refs.forEach(ref => { if (ref.current) ro.observe(ref.current) })
    return () => ro.disconnect()
  }, [refs, charts])
}

// ── Volume chart ──────────────────────────────────────────────────────────────

function VolumeChart({ data, n }: { data: IndicatorResponse; n: number }) {
  const topRef = useRef<HTMLDivElement>(null)
  const botRef = useRef<HTMLDivElement>(null)
  const charts = useRef<(IChartApi | null)[]>([null, null])

  useResizeObserver([topRef, botRef], charts)

  useEffect(() => {
    if (!topRef.current || !botRef.current) return
    charts.current.forEach(c => c?.remove())

    const top = createChart(topRef.current, chartOpts(topRef.current.clientWidth, 400))
    const bot = createChart(botRef.current, { ...chartOpts(botRef.current.clientWidth, 160), timeScale: { borderColor: T.border, timeVisible: true } })
    charts.current = [top, bot]

    addPricePanel(top, data, n)

    const candles = sliceCandles(data.candles, n)
    const volSeries = bot.addHistogramSeries({
      priceFormat: { type: 'volume' },
      priceScaleId: '',
    })
    volSeries.priceScale().applyOptions({ scaleMargins: { top: 0.1, bottom: 0 } })
    volSeries.setData(candles.map((c, i) => ({
      time: c.time as import('lightweight-charts').Time,
      value: c.volume,
      color: c.close >= (i > 0 ? candles[i - 1].close : c.close) ? C.volUp : C.volDown,
    })))
    if (data.vol_ma?.length) {
      addLine(bot, sliceLine(data.vol_ma, n), { color: C.volMa, lineWidth: 1 })
    }

    syncCharts([top, bot])
    top.timeScale().fitContent()

    return () => { charts.current.forEach(c => c?.remove()); charts.current = [null, null] }
  }, [data, n])

  return (
    <div>
      <div ref={topRef} className="chart-pane" />
      <div ref={botRef} className="chart-pane" />
    </div>
  )
}

// ── Score chart ───────────────────────────────────────────────────────────────

function ScoreChart({ data, n }: { data: IndicatorResponse; n: number }) {
  const topRef = useRef<HTMLDivElement>(null)
  const botRef = useRef<HTMLDivElement>(null)
  const charts = useRef<(IChartApi | null)[]>([null, null])

  useResizeObserver([topRef, botRef], charts)

  useEffect(() => {
    if (!topRef.current || !botRef.current) return
    charts.current.forEach(c => c?.remove())

    const top = createChart(topRef.current, chartOpts(topRef.current.clientWidth, 400))
    const bot = createChart(botRef.current, chartOpts(botRef.current.clientWidth, 160))
    charts.current = [top, bot]

    addPricePanel(top, data, n)
    addDivergenceLines(top, data.div_score ?? [], true)

    const scoreData = sliceLine(data.score, n)
    if (scoreData.length) {
      addLine(bot, scoreData, { color: C.score, lineWidth: 2 })
    }
    addDivergenceLines(bot, data.div_score ?? [], false)

    // Reference lines on score panel
    const lastScore = scoreData[scoreData.length - 1]?.value ?? 0
    for (const [val, color] of [[30, '#3a5a3a'], [-30, '#5a3a3a'], [70, '#f87171'], [-70, '#4ade80'], [10, '#2a3a2a'], [-10, '#3a2a2a']] as [number, string][]) {
      const s = bot.addLineSeries({ color, lineWidth: 1, lineStyle: val === 10 || val === -10 ? LineStyle.Dotted : LineStyle.Dashed, priceLineVisible: false, lastValueVisible: false })
      s.setData(scoreData.map(d => ({ time: d.time, value: val })))
    }
    void lastScore

    syncCharts([top, bot])
    top.timeScale().fitContent()

    return () => { charts.current.forEach(c => c?.remove()); charts.current = [null, null] }
  }, [data, n])

  return (
    <div>
      <div ref={topRef} className="chart-pane" />
      <div ref={botRef} className="chart-pane" />
    </div>
  )
}

// ── RSI chart ─────────────────────────────────────────────────────────────────

function RsiChart({ data, n }: { data: IndicatorResponse; n: number }) {
  const topRef = useRef<HTMLDivElement>(null)
  const botRef = useRef<HTMLDivElement>(null)
  const charts = useRef<(IChartApi | null)[]>([null, null])

  useResizeObserver([topRef, botRef], charts)

  useEffect(() => {
    if (!topRef.current || !botRef.current) return
    charts.current.forEach(c => c?.remove())

    const top = createChart(topRef.current, chartOpts(topRef.current.clientWidth, 400))
    const bot = createChart(botRef.current, chartOpts(botRef.current.clientWidth, 160))
    charts.current = [top, bot]

    addPricePanel(top, data, n)
    addDivergenceLines(top, data.div_rsi ?? [], true)

    const rsiData = sliceLine(data.rsi, n)
    if (rsiData.length) {
      addLine(bot, rsiData, { color: C.rsi, lineWidth: 2 })
    }
    if (data.rsi_ma?.length) {
      addLine(bot, sliceLine(data.rsi_ma, n), { color: C.rsiMa, lineWidth: 1, lineStyle: LineStyle.Dashed })
    }
    addDivergenceLines(bot, data.div_rsi ?? [], false)

    for (const [val, color] of [[70, '#f87171'], [50, T.muted], [30, '#4ade80']] as [number, string][]) {
      const s = bot.addLineSeries({ color, lineWidth: 1, lineStyle: val === 50 ? LineStyle.Dotted : LineStyle.Dashed, priceLineVisible: false, lastValueVisible: false })
      s.setData(rsiData.map(d => ({ time: d.time, value: val })))
    }

    syncCharts([top, bot])
    top.timeScale().fitContent()

    return () => { charts.current.forEach(c => c?.remove()); charts.current = [null, null] }
  }, [data, n])

  return (
    <div>
      <div ref={topRef} className="chart-pane" />
      <div ref={botRef} className="chart-pane" />
    </div>
  )
}

// ── StochRSI chart ────────────────────────────────────────────────────────────

function StochChart({ data, n }: { data: IndicatorResponse; n: number }) {
  const topRef  = useRef<HTMLDivElement>(null)
  const mid1Ref = useRef<HTMLDivElement>(null)
  const mid2Ref = useRef<HTMLDivElement>(null)
  const charts  = useRef<(IChartApi | null)[]>([null, null, null])

  useResizeObserver([topRef, mid1Ref, mid2Ref], charts)

  useEffect(() => {
    if (!topRef.current || !mid1Ref.current || !mid2Ref.current) return
    charts.current.forEach(c => c?.remove())

    const top  = createChart(topRef.current,  chartOpts(topRef.current.clientWidth,  380))
    const mid1 = createChart(mid1Ref.current, chartOpts(mid1Ref.current.clientWidth, 150))
    const mid2 = createChart(mid2Ref.current, chartOpts(mid2Ref.current.clientWidth, 150))
    charts.current = [top, mid1, mid2]

    addPricePanel(top, data, n)

    const pairs: [React.RefObject<HTMLDivElement>, IChartApi, string, string, string][] = [
      [mid1Ref, mid1, 'srsi_k_0', 'srsi_d_0', 'Slow StochRSI'],
      [mid2Ref, mid2, 'srsi_k_1', 'srsi_d_1', 'Fast StochRSI'],
    ]

    for (const [, chart, kKey, dKey] of pairs) {
      const kData = sliceLine((data as unknown as Record<string, LinePoint[]>)[kKey] ?? [], n)
      const dData = sliceLine((data as unknown as Record<string, LinePoint[]>)[dKey] ?? [], n)

      if (kData.length) addLine(chart, kData, { color: C.kLine, lineWidth: 2 })
      if (dData.length) addLine(chart, dData, { color: C.dLine, lineWidth: 1, lineStyle: LineStyle.Dashed })

      for (const [val, color] of [[80, '#f87171'], [20, '#4ade80']] as [number, string][]) {
        const ref = kData.length ? kData : dData
        if (ref.length) {
          const s = chart.addLineSeries({ color, lineWidth: 1, lineStyle: LineStyle.Dashed, priceLineVisible: false, lastValueVisible: false })
          s.setData(ref.map(d => ({ time: d.time, value: val })))
        }
      }
    }

    syncCharts([top, mid1, mid2])
    top.timeScale().fitContent()

    return () => { charts.current.forEach(c => c?.remove()); charts.current = [null, null, null] }
  }, [data, n])

  return (
    <div>
      <div ref={topRef}  className="chart-pane" />
      <div ref={mid1Ref} className="chart-pane" />
      <div ref={mid2Ref} className="chart-pane" />
    </div>
  )
}

// ── OBV chart ─────────────────────────────────────────────────────────────────

function ObvChart({ data, n }: { data: IndicatorResponse; n: number }) {
  const topRef = useRef<HTMLDivElement>(null)
  const botRef = useRef<HTMLDivElement>(null)
  const charts = useRef<(IChartApi | null)[]>([null, null])

  useResizeObserver([topRef, botRef], charts)

  useEffect(() => {
    if (!topRef.current || !botRef.current) return
    charts.current.forEach(c => c?.remove())

    const top = createChart(topRef.current, chartOpts(topRef.current.clientWidth, 400))
    const bot = createChart(botRef.current, chartOpts(botRef.current.clientWidth, 160))
    charts.current = [top, bot]

    addPricePanel(top, data, n)
    addDivergenceLines(top, data.div_obv ?? [], true)

    if (data.obv?.length) {
      addLine(bot, sliceLine(data.obv, n), { color: C.obv, lineWidth: 2 })
    }
    if (data.obv_ma?.length) {
      addLine(bot, sliceLine(data.obv_ma, n), { color: C.obvMa, lineWidth: 1, lineStyle: LineStyle.Dashed })
    }
    addDivergenceLines(bot, data.div_obv ?? [], false)

    syncCharts([top, bot])
    top.timeScale().fitContent()

    return () => { charts.current.forEach(c => c?.remove()); charts.current = [null, null] }
  }, [data, n])

  return (
    <div>
      <div ref={topRef} className="chart-pane" />
      <div ref={botRef} className="chart-pane" />
    </div>
  )
}

// ── Keltner/CNV chart ─────────────────────────────────────────────────────────

function KeltnerChart({ data, n }: { data: IndicatorResponse; n: number }) {
  const topRef = useRef<HTMLDivElement>(null)
  const botRef = useRef<HTMLDivElement>(null)
  const charts = useRef<(IChartApi | null)[]>([null, null])

  useResizeObserver([topRef, botRef], charts)

  useEffect(() => {
    if (!topRef.current || !botRef.current) return
    charts.current.forEach(c => c?.remove())

    const top = createChart(topRef.current, chartOpts(topRef.current.clientWidth, 400))
    const bot = createChart(botRef.current, chartOpts(botRef.current.clientWidth, 160))
    charts.current = [top, bot]

    // Price panel: candles + KC + NW only (no MAs like in the GUI)
    const candles = sliceCandles(data.candles, n)
    const cs = top.addCandlestickSeries({
      upColor: '#4ade80', downColor: '#f87171',
      borderUpColor: '#4ade80', borderDownColor: '#f87171',
      wickUpColor: '#4ade80', wickDownColor: '#f87171',
    } as Partial<CandlestickSeriesOptions>)
    cs.setData(candles)

    if (data.kc_upper?.length) addLine(top, sliceLine(data.kc_upper, n), { color: C.kc, lineWidth: 1 })
    if (data.kc_basis?.length) addLine(top, sliceLine(data.kc_basis, n), { color: C.kc, lineWidth: 1, lineStyle: LineStyle.Dashed })
    if (data.kc_lower?.length) addLine(top, sliceLine(data.kc_lower, n), { color: C.kc, lineWidth: 1 })
    if (data.nw_upper?.length) addLine(top, sliceLine(data.nw_upper, n), { color: C.nw, lineWidth: 1, lineStyle: LineStyle.Dotted })
    if (data.nw_lower?.length) addLine(top, sliceLine(data.nw_lower, n), { color: '#f87171', lineWidth: 1, lineStyle: LineStyle.Dotted })

    // 17-bar and 42-bar reference price lines
    if (data.price_17 != null && candles.length) {
      const s = top.addLineSeries({ color: '#a855f7', lineWidth: 1, lineStyle: LineStyle.Dashed, priceLineVisible: false, lastValueVisible: true })
      s.setData(candles.map(c => ({ time: c.time as import('lightweight-charts').Time, value: data.price_17! })))
    }
    if (data.price_42 != null && candles.length) {
      const s = top.addLineSeries({ color: '#60a5fa', lineWidth: 1, lineStyle: LineStyle.Dashed, priceLineVisible: false, lastValueVisible: true })
      s.setData(candles.map(c => ({ time: c.time as import('lightweight-charts').Time, value: data.price_42! })))
    }

    // CNV histogram
    if (data.cnv?.length) {
      const cnvData = sliceLine(data.cnv, n)
      const hist = bot.addHistogramSeries({ priceScaleId: 'right' })
      hist.setData(cnvData.map(d => ({
        time: d.time as import('lightweight-charts').Time,
        value: d.value,
        color: d.value >= 0 ? C.cnvBull : C.cnvBear,
      })))
    }

    syncCharts([top, bot])
    top.timeScale().fitContent()

    return () => { charts.current.forEach(c => c?.remove()); charts.current = [null, null] }
  }, [data, n])

  return (
    <div>
      <div ref={topRef} className="chart-pane" />
      <div ref={botRef} className="chart-pane" />
    </div>
  )
}

// ── Charts (main) ─────────────────────────────────────────────────────────────

const SUB_TABS = ['Volume', 'Score', 'RSI', 'Stoch RSI', 'OBV', 'Keltner'] as const
type SubTab = typeof SUB_TABS[number]

export default function Charts({ customTickers = [] }: { customTickers?: string[] }) {
  const allTickers = [...TICKER_KEYS, ...customTickers.filter(s => !TICKER_KEYS.includes(s))]
  const [ticker,   setTicker]   = useState<string>(TICKER_KEYS[0])
  const [interval, setInterval] = useState<Interval>('1d')
  const [lookback, setLookback] = useState<string>(DEFAULT_LOOKBACK['1d'])
  const [subTab,   setSubTab]   = useState<SubTab>('Volume')
  const [data,     setData]     = useState<IndicatorResponse | null>(null)
  const [loading,  setLoading]  = useState(false)
  const [error,    setError]    = useState<string | null>(null)

  const n = LOOKBACK_BARS[lookback]?.[interval] ?? 0

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    fetchIndicators(ticker, interval)
      .then(setData)
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false))
  }, [ticker, interval])

  useEffect(() => { load() }, [load])

  // Reset lookback default when interval changes
  useEffect(() => {
    setLookback(DEFAULT_LOOKBACK[interval])
  }, [interval])

  return (
    <div className="charts-wrap">
      <div className="controls">
        <div className="ctrl-group">
          <span className="ctrl-label">TICKER</span>
          <select
            value={ticker}
            onChange={e => setTicker(e.target.value)}
            style={{
              background: 'var(--surface)',
              border: '1px solid var(--border)',
              color: 'var(--text)',
              fontFamily: 'inherit',
              fontSize: 11,
              padding: '3px 8px',
              height: 24,
              cursor: 'pointer',
            }}
          >
            {allTickers.map(k => <option key={k} value={k}>{k}</option>)}
          </select>
        </div>

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

        <div className="ctrl-group">
          <span className="ctrl-label">LOOKBACK</span>
          {Object.keys(LOOKBACK_BARS).map(lb => (
            <button
              key={lb}
              className={`seg-btn${lookback === lb ? ' active' : ''}`}
              onClick={() => setLookback(lb)}
            >
              {lb}
            </button>
          ))}
        </div>
      </div>

      <div className="chart-tabs">
        {SUB_TABS.map(t => (
          <button
            key={t}
            className={`chart-tab${subTab === t ? ' active' : ''}`}
            onClick={() => setSubTab(t)}
          >
            {t}
          </button>
        ))}
      </div>

      <div className="chart-area" style={{ overflowY: 'auto' }}>
        {loading && <div className="status">loading...</div>}
        {error   && <div className="status">error: {error}</div>}
        {data && !loading && (
          <>
            {subTab === 'Volume'   && <VolumeChart   data={data} n={n} />}
            {subTab === 'Score'    && <ScoreChart    data={data} n={n} />}
            {subTab === 'RSI'      && <RsiChart      data={data} n={n} />}
            {subTab === 'Stoch RSI'&& <StochChart    data={data} n={n} />}
            {subTab === 'OBV'      && <ObvChart      data={data} n={n} />}
            {subTab === 'Keltner'  && <KeltnerChart  data={data} n={n} />}
          </>
        )}
      </div>
    </div>
  )
}
