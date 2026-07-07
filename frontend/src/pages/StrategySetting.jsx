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
          <p>포지션 크기, 진입 기준, 손실 제한을 한 곳에서 조정</p>
        </div>
        <button onClick={save} style={{ color: 'var(--blue)', borderColor: 'var(--blue)' }}>{saved ? '저장됨' : '저장'}</button>
      </div>
      <div style={S.sections}>
        <SettingGroup title="주문 크기" note="한 번 진입할 때 실제로 넣는 수량과 레버리지">
          <Field label="1회 주문 수량" hint="BTC 단위" value={form.order_size_btc} step="0.001" onChange={(v) => set('order_size_btc', v)} />
          <Field label="최대 레버리지" hint="자동매매 상한" value={form.max_leverage} step="1" onChange={(v) => set('max_leverage', Math.trunc(v))} />
        </SettingGroup>

        <SettingGroup title="진입 조건" note="신호가 떠도 이 기준을 넘겨야 자동 진입">
          <Field label="신뢰도 기준" hint="% 이상일 때 진입" value={form.confidence_threshold} step="5" onChange={(v) => set('confidence_threshold', v)} />
          <Field label="재진입 대기" hint="초 단위" value={form.reentry_wait_seconds} step="60" onChange={(v) => set('reentry_wait_seconds', Math.trunc(v))} />
        </SettingGroup>

        <SettingGroup title="손실 보호" note="연속 손실이나 큰 손실이 나면 자동매매 차단">
          <Field label="1회 최대 손실률" hint="% 초과 시 진입 차단" value={form.max_loss_pct} step="0.5" onChange={(v) => set('max_loss_pct', v)} />
          <Field label="일일 최대 손실률" hint="% 도달 시 당일 중지" value={form.daily_max_loss_pct} step="1" onChange={(v) => set('daily_max_loss_pct', v)} />
          <Field label="연속 손실 정지" hint="횟수 도달 시 중지" value={form.consecutive_loss_limit} step="1" onChange={(v) => set('consecutive_loss_limit', Math.trunc(v))} />
        </SettingGroup>

        <SettingGroup title="실거래 안전장치" note="꺼져 있으면 LIVE 모드에서도 실주문을 막음">
          <label style={S.switchRow}>
            <span>
              <strong style={S.mainLabel}>실거래 주문 허용</strong>
              <span style={S.hint}>{form.live_trading_allowed ? '실주문 가능' : '실주문 차단'}</span>
            </span>
            <input type="checkbox" checked={Boolean(form.live_trading_allowed)} onChange={(e) => set('live_trading_allowed', e.target.checked)} />
          </label>
        </SettingGroup>
      </div>
    </section>
  )
}

function SettingGroup({ title, note, children }) {
  return (
    <div style={S.group}>
      <div style={S.groupHeader}>
        <strong>{title}</strong>
        <span>{note}</span>
      </div>
      <div style={S.groupBody}>{children}</div>
    </div>
  )
}

function Field({ label, hint, value, step, onChange }) {
  return (
    <label style={S.row}>
      <span>
        <strong style={S.mainLabel}>{label}</strong>
        <span style={S.hint}>{hint}</span>
      </span>
      <input type="number" value={value} step={step} onChange={(e) => onChange(Number(e.target.value))} style={S.input} />
    </label>
  )
}

const S = {
  sections: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 12 },
  group: { border: '1px solid var(--border-soft)', borderRadius: 8, background: 'rgba(255,255,255,0.024)', overflow: 'hidden' },
  groupHeader: { display: 'grid', gap: 4, padding: '12px 14px', borderBottom: '1px solid var(--border-soft)', background: 'rgba(101,183,255,0.055)', color: 'var(--text)' },
  groupBody: { display: 'grid', gap: 8, padding: 10 },
  row: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, border: '1px solid var(--border-soft)', borderRadius: 8, padding: '10px 12px', background: 'var(--card)' },
  switchRow: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, border: '1px solid rgba(101,183,255,0.32)', borderRadius: 8, padding: '12px', background: 'var(--blue-dim)' },
  mainLabel: { display: 'block', color: 'var(--text)', fontSize: 13, marginBottom: 3 },
  hint: { display: 'block', color: 'var(--text2)', fontSize: 11 },
  input: { width: 120 },
}
