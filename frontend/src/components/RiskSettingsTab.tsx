import { useEffect, useState } from 'react'
import type { RiskSettings } from '../types'
import { api } from '../api'

interface Props { settings: RiskSettings | null }

export function RiskSettingsTab({ settings }: Props) {
  const [s, setS] = useState<RiskSettings>(settings ?? {
    order_size_btc: 0.001, max_loss_pct: 1.0, daily_max_loss_pct: 3.0,
    consecutive_loss_limit: 3, confidence_threshold: 30.0, reentry_wait_seconds: 300,
    max_leverage: 3, live_trading_allowed: false,
  })
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    if (settings) setS(settings)
  }, [settings])

  if (!settings) return <div style={{ color: 'var(--text2)', padding: 20 }}>설정을 불러오는 중…</div>

  const set = <K extends keyof RiskSettings>(k: K, v: RiskSettings[K]) => setS((prev) => ({ ...prev, [k]: v }))

  const handleSave = async () => {
    await api.saveRiskSettings(s)
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  const Row = ({ label, children }: { label: string; children: React.ReactNode }) => (
    <div style={S.row}><span style={S.label}>{label}</span>{children}</div>
  )

  return (
    <div style={S.form}>
      <Row label="1회 주문 수량 (BTC)">
        <input type="number" min="0.001" max="10" step="0.001" value={s.order_size_btc} onChange={(e) => set('order_size_btc', parseFloat(e.target.value))} style={S.input} />
      </Row>
      <Row label="1회 최대 손실률 (%)">
        <input type="number" min="0.1" max="50" step="0.5" value={s.max_loss_pct} onChange={(e) => set('max_loss_pct', parseFloat(e.target.value))} style={S.input} />
      </Row>
      <Row label="일일 최대 손실률 (%)">
        <input type="number" min="0.1" max="100" step="1" value={s.daily_max_loss_pct} onChange={(e) => set('daily_max_loss_pct', parseFloat(e.target.value))} style={S.input} />
      </Row>
      <Row label="연속 손실 정지 횟수">
        <input type="number" min="1" max="20" step="1" value={s.consecutive_loss_limit} onChange={(e) => set('consecutive_loss_limit', parseInt(e.target.value))} style={S.input} />
      </Row>
      <Row label="자동매매 신뢰도 기준 (%)">
        <input type="number" min="0" max="99" step="5" value={s.confidence_threshold} onChange={(e) => set('confidence_threshold', parseFloat(e.target.value))} style={S.input} />
      </Row>
      <Row label="재진입 대기 시간 (초)">
        <input type="number" min="0" max="3600" step="60" value={s.reentry_wait_seconds} onChange={(e) => set('reentry_wait_seconds', parseInt(e.target.value))} style={S.input} />
      </Row>
      <Row label="최대 레버리지">
        <input type="number" min="1" max="125" step="1" value={s.max_leverage} onChange={(e) => set('max_leverage', parseInt(e.target.value))} style={S.input} />
      </Row>
      <Row label="실거래 주문 허용">
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
          <input type="checkbox" checked={s.live_trading_allowed} onChange={(e) => set('live_trading_allowed', e.target.checked)} />
          <span style={{ fontSize: 12, color: s.live_trading_allowed ? 'var(--red)' : 'var(--text2)' }}>
            {s.live_trading_allowed ? '⚠ 실거래 허용됨 — 실제 주문이 발생합니다' : '비활성화 (안전)'}
          </span>
        </label>
      </Row>
      <div style={{ marginTop: 16 }}>
        <button onClick={handleSave} style={{ borderColor: 'var(--blue)', color: 'var(--blue)' }}>
          {saved ? '✓ 저장됨' : '설정 저장'}
        </button>
      </div>
    </div>
  )
}

const S: Record<string, React.CSSProperties> = {
  form: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 10, paddingTop: 4 },
  row: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, background: 'rgba(255,255,255,0.026)', border: '1px solid var(--border-soft)', borderRadius: 8, padding: '10px 12px' },
  label: { minWidth: 140, fontSize: 13, color: 'var(--text2)' },
  input: { width: 130 },
}
