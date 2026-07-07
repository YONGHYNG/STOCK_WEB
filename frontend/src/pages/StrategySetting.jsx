// 역할: 매매 전략 설정과 조건값을 조정하는 화면.
import { useEffect, useState } from 'react'
import { tradingApi } from '../api/tradingApi'

const DEFAULTS = {
  order_size_btc: 0.001,
  max_loss_pct: 1,
  daily_max_loss_pct: 3,
  consecutive_loss_limit: 3,
  confidence_threshold: 30,
  reentry_wait_seconds: 300,
  max_leverage: 3,
  live_trading_allowed: false,
}

export function StrategySetting({ settings, onSaved }) {
  const [form, setForm] = useState(settings ?? DEFAULTS)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    if (settings) setForm(settings)
  }, [settings])

  function set(key, value) {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  async function save() {
    await tradingApi.saveRiskSettings(form)
    setSaved(true)
    onSaved?.(form)
    setTimeout(() => setSaved(false), 1600)
  }

  return (
    <section className="workspace-panel">
      <div className="workspace-panel__top">
        <div>
          <h2>전략 및 리스크 설정</h2>
          <p>자동매매 진입 조건과 손실 제한 기준</p>
        </div>
        <button onClick={save} style={{ color: 'var(--blue)', borderColor: 'var(--blue)' }}>{saved ? '저장됨' : '저장'}</button>
      </div>
      <div style={S.form}>
        <Field label="1회 주문 수량 BTC" value={form.order_size_btc} step="0.001" onChange={(v) => set('order_size_btc', v)} />
        <Field label="1회 최대 손실률 %" value={form.max_loss_pct} step="0.5" onChange={(v) => set('max_loss_pct', v)} />
        <Field label="일일 최대 손실률 %" value={form.daily_max_loss_pct} step="1" onChange={(v) => set('daily_max_loss_pct', v)} />
        <Field label="연속 손실 정지 횟수" value={form.consecutive_loss_limit} step="1" onChange={(v) => set('consecutive_loss_limit', Math.trunc(v))} />
        <Field label="신뢰도 기준 %" value={form.confidence_threshold} step="5" onChange={(v) => set('confidence_threshold', v)} />
        <Field label="재진입 대기 초" value={form.reentry_wait_seconds} step="60" onChange={(v) => set('reentry_wait_seconds', Math.trunc(v))} />
        <Field label="최대 레버리지" value={form.max_leverage} step="1" onChange={(v) => set('max_leverage', Math.trunc(v))} />
        <label style={S.row}>
          <span style={S.label}>실거래 주문 허용</span>
          <input type="checkbox" checked={Boolean(form.live_trading_allowed)} onChange={(e) => set('live_trading_allowed', e.target.checked)} />
        </label>
      </div>
    </section>
  )
}

function Field({ label, value, step, onChange }) {
  return (
    <label style={S.row}>
      <span style={S.label}>{label}</span>
      <input type="number" value={value} step={step} onChange={(e) => onChange(Number(e.target.value))} style={S.input} />
    </label>
  )
}

const S = {
  form: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 10 },
  row: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, border: '1px solid var(--border-soft)', borderRadius: 8, padding: '10px 12px', background: 'rgba(255,255,255,0.026)' },
  label: { color: 'var(--text2)', fontSize: 13 },
  input: { width: 120 },
}
