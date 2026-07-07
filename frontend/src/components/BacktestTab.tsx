import { useState } from 'react'
import { api } from '../api'

interface TradeLog { entry_ts: number; exit_ts: number; direction: string; entry_px: number; exit_px: number; result: string; pnl_pct: number }
interface BacktestResult { total_trades: number; win_trades: number; loss_trades: number; win_rate: number; cumulative_return_pct: number; avg_win_pct: number; avg_loss_pct: number; max_drawdown_pct: number; profit_factor: number; tp_trades: number; sl_trades: number; final_capital: number }

export function BacktestTab() {
  const today = new Date()
  const ninetyAgo = new Date(today.getTime() - 90 * 86400 * 1000)
  const toIso = (d: Date) => d.toISOString().slice(0, 10)

  const [startDate, setStartDate] = useState(toIso(ninetyAgo))
  const [endDate, setEndDate] = useState(toIso(today))
  const [timeframe, setTimeframe] = useState('1H')
  const [capital, setCapital] = useState(10000)
  const [fee, setFee] = useState(0.05)
  const [slip, setSlip] = useState(0.02)
  const [sizePct, setSizePct] = useState(10)
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<BacktestResult | null>(null)
  const [tradeLog, setTradeLog] = useState<TradeLog[]>([])
  const [error, setError] = useState('')

  const runBacktest = async () => {
    setRunning(true); setError(''); setResult(null); setTradeLog([])
    const startTs = new Date(startDate).getTime()
    const endTs = new Date(endDate + 'T23:59:59').getTime()
    const res = await api.runBacktest({
      start_ts: startTs, end_ts: endTs, timeframe,
      initial_capital: capital, fee_rate: fee / 100,
      slippage: slip / 100, order_size_pct: sizePct,
    })
    setRunning(false)
    if (!res.ok) { setError(res.error ?? '알 수 없는 오류'); return }
    setResult(res.result as unknown as BacktestResult)
    setTradeLog((res.trade_log ?? []) as TradeLog[])
  }

  const tsStr = (ts: number) => new Date(ts).toLocaleString('ko-KR', { dateStyle: 'short', timeStyle: 'short' })

  return (
    <div>
      <div style={S.cfg}>
        <div style={S.cfgGroup}>
          <label style={S.lbl}>시작일</label>
          <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} style={S.inp} />
          <label style={S.lbl}>종료일</label>
          <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} style={S.inp} />
        </div>
        <div style={S.cfgGroup}>
          <label style={S.lbl}>시간봉</label>
          <select value={timeframe} onChange={(e) => setTimeframe(e.target.value)} style={S.inp}>
            {['5m', '15m', '30m', '1H', '6H', '1D'].map((t) => <option key={t}>{t}</option>)}
          </select>
          <label style={S.lbl}>초기 자본</label>
          <input type="number" value={capital} onChange={(e) => setCapital(Number(e.target.value))} style={{ ...S.inp, width: 110 }} />
        </div>
        <div style={S.cfgGroup}>
          <label style={S.lbl}>수수료 (%)</label>
          <input type="number" step="0.01" value={fee} onChange={(e) => setFee(Number(e.target.value))} style={S.inp} />
          <label style={S.lbl}>슬리피지 (%)</label>
          <input type="number" step="0.01" value={slip} onChange={(e) => setSlip(Number(e.target.value))} style={S.inp} />
          <label style={S.lbl}>주문비율 (%)</label>
          <input type="number" step="5" value={sizePct} onChange={(e) => setSizePct(Number(e.target.value))} style={S.inp} />
        </div>
        <button onClick={runBacktest} disabled={running} style={{ alignSelf: 'flex-end', padding: '8px 18px', borderColor: 'var(--green)', color: 'var(--green)' }}>
          {running ? '실행 중…' : '▶ 백테스트 실행'}
        </button>
      </div>

      {error && <div style={{ color: 'var(--red)', padding: '8px 0' }}>오류: {error}</div>}

      {result && (
        <div style={S.summary}>
          <span>총 거래: <b>{result.total_trades}</b></span>
          <span>승률: <b style={{ color: 'var(--green)' }}>{result.win_rate.toFixed(1)}%</b></span>
          <span>누적수익: <b style={{ color: result.cumulative_return_pct >= 0 ? 'var(--green)' : 'var(--red)' }}>{result.cumulative_return_pct >= 0 ? '+' : ''}{result.cumulative_return_pct.toFixed(2)}%</b></span>
          <span>MDD: <b style={{ color: 'var(--red)' }}>{result.max_drawdown_pct.toFixed(2)}%</b></span>
          <span>손익비: <b style={{ color: 'var(--yellow)' }}>{result.profit_factor.toFixed(2)}</b></span>
          <span>최종 자본: <b>${result.final_capital.toLocaleString('en-US', { minimumFractionDigits: 2 })}</b></span>
        </div>
      )}

      {tradeLog.length > 0 && (
        <div className="data-table-wrap">
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
            <thead>
              <tr>{['진입시각', '청산시각', '방향', '진입가', '청산가', '결과', '수익률'].map((h) => (
                <th key={h} style={S.th}>{h}</th>
              ))}</tr>
            </thead>
            <tbody>
              {tradeLog.map((t, i) => {
                const pnlColor = t.pnl_pct >= 0 ? 'var(--green)' : 'var(--red)'
                const rc: Record<string, string> = { TP1: 'var(--green)', TP2: 'var(--green)', SL: 'var(--red)', FORCED_CLOSE: 'var(--yellow)' }
                return (
                  <tr key={i}>
                    <td style={S.td}>{tsStr(t.entry_ts)}</td>
                    <td style={S.td}>{tsStr(t.exit_ts)}</td>
                    <td style={{ ...S.td, color: t.direction === 'LONG' ? 'var(--green)' : 'var(--red)' }}>{t.direction}</td>
                    <td style={S.td}>${t.entry_px.toLocaleString('en-US', { minimumFractionDigits: 2 })}</td>
                    <td style={S.td}>${t.exit_px.toLocaleString('en-US', { minimumFractionDigits: 2 })}</td>
                    <td style={{ ...S.td, color: rc[t.result] ?? 'var(--text2)' }}>{t.result}</td>
                    <td style={{ ...S.td, color: pnlColor }}>{t.pnl_pct >= 0 ? '+' : ''}{t.pnl_pct.toFixed(3)}%</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

const S: Record<string, React.CSSProperties> = {
  cfg: { display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'flex-end', marginBottom: 12, paddingBottom: 12, borderBottom: '1px solid var(--border-soft)' },
  cfgGroup: { display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center', background: 'rgba(255,255,255,0.026)', border: '1px solid var(--border-soft)', borderRadius: 8, padding: 8 },
  lbl: { fontSize: 12, color: 'var(--text2)' },
  inp: { width: 100 },
  summary: { display: 'flex', flexWrap: 'wrap', gap: 12, padding: '10px 0', fontSize: 14, borderBottom: '1px solid var(--border-soft)', marginBottom: 8 },
  th: { padding: '8px 9px', textAlign: 'left', color: 'var(--text2)', fontWeight: 800, borderBottom: '1px solid var(--border)', background: 'var(--card)', position: 'sticky', top: 0 },
  td: { padding: '7px 9px', borderBottom: '1px solid var(--border-soft)', color: 'var(--text)', whiteSpace: 'nowrap' },
}
