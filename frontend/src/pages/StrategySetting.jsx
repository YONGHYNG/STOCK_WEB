// 역할: 매매 전략 설정과 조건값을 조정하는 화면.
import { useEffect, useState } from 'react'
import { tradingApi } from '../api/tradingApi'

const DEFAULTS = {
  order_size_btc: 0.001,
  max_loss_pct: 1,
  daily_max_loss_pct: 3,
  consecutive_loss_limit: 3,
  confidence_threshold: 30,
  reentry_wait_seconds: 30,
  stop_gap_min_usdt: 400,
  stop_gap_max_usdt: 700,
  take_profit_1_min_usdt: 500,
  take_profit_1_max_usdt: 600,
  take_profit_2_usdt: 800,
  max_leverage: 3,
  live_trading_allowed: false,
}

function minutesLabel(seconds) {
  if (!seconds) return '즉시'
  return seconds >= 60 ? `약 ${(seconds / 60).toFixed(seconds % 60 ? 1 : 0)}분` : `${seconds}초`
}

export function StrategySetting({ settings, onSaved }) {
  const [form, setForm] = useState(settings ?? DEFAULTS)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    if (settings) setForm(settings)
  }, [settings])

  const dirty = JSON.stringify(form) !== JSON.stringify(settings ?? DEFAULTS)

  function set(key, value) {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  async function save() {
    await tradingApi.saveRiskSettings(form)
    setSaved(true)
    onSaved?.(form)
    setTimeout(() => setSaved(false), 1600)
  }

  const leverageWarn = form.max_leverage > 5
  const dailyLossWarn = form.daily_max_loss_pct > 10
  const confidenceWarn = form.confidence_threshold > 100

  return (
    <section className="workspace-panel">
      <div className="workspace-panel__top">
        <div>
          <h2>전략 및 리스크 설정</h2>
          <p>자동매매가 언제, 얼마나, 어디까지 움직일지 여기서 정해요</p>
        </div>
        <div className="save-area">
          {dirty && !saved && <span className="dirty-tag">저장되지 않은 변경사항</span>}
          <button onClick={save} className={saved ? 'tone-long' : 'tone-info'} style={{ borderColor: 'currentColor' }}>
            {saved ? '저장됨 ✓' : '저장하기'}
          </button>
        </div>
      </div>

      <div className="settings-summary">
        <div className="settings-summary__title">지금 설정을 말로 풀면</div>
        <ul className="settings-summary__list">
          <li>확정 진입 신호가 나온 뒤 리스크 검사를 통과할 때만, 최대 <b>{form.max_leverage}배</b> 레버리지로 <b>{form.order_size_btc} BTC</b>씩 자동 진입해요</li>
          <li>한 번에 <b>{form.max_loss_pct}%</b> 넘게 잃거나 하루 합계로 <b>{form.daily_max_loss_pct}%</b> 잃으면 그날은 더 이상 진입하지 않아요</li>
          <li>손실이 <b>{form.consecutive_loss_limit}번</b> 연속되면 잠시 멈추고, 다음 진입까지는 <b>{minutesLabel(form.reentry_wait_seconds)}</b> 기다려요</li>
          <li>진입가 기준 손절 간격은 <b>{form.stop_gap_min_usdt}~{form.stop_gap_max_usdt} USDT</b>, 익절 간격은 <b>{form.take_profit_1_min_usdt}~{form.take_profit_1_max_usdt} / {form.take_profit_2_usdt} USDT</b>로 잡아요</li>
          <li>실거래 주문은 지금 <b className={form.live_trading_allowed ? 'tone-short' : 'tone-long'}>{form.live_trading_allowed ? '허용됨 (실제 돈이 움직여요)' : '차단됨 (신호만 보여줘요)'}</b></li>
        </ul>
      </div>

      <div className="settings-sections">
        <SettingGroup title="주문 크기" note="한 번 진입할 때 실제로 넣는 수량과 레버리지 배수예요">
          <Field
            label="1회 주문 수량"
            hint="자동매매가 신호 하나당 실제로 매매하는 BTC 수량이에요"
            value={form.order_size_btc}
            step="0.001"
            min="0.001"
            suffix="BTC"
            onChange={(v) => set('order_size_btc', v)}
          />
          <Field
            label="최대 레버리지"
            hint="원금 대비 몇 배까지 크게 베팅할지 정해요. 높을수록 수익도 손실도 커져요"
            value={form.max_leverage}
            step="1"
            min="1"
            suffix="배"
            onChange={(v) => set('max_leverage', Math.trunc(v))}
            warn={leverageWarn}
            warnText="5배가 넘으면 작은 가격 변동에도 청산 위험이 크게 늘어나요"
          />
        </SettingGroup>

        <SettingGroup title="손절·익절 가격 간격" note="실제 손익금이 아니라 BTC 진입가에서 떨어진 USDT 가격 간격이에요">
          <Field label="최소 손절 간격" hint="ATR이 작아도 이 가격 간격보다 손절을 좁히지 않아요" value={form.stop_gap_min_usdt} step="50" min="1" suffix="USDT" onChange={(v) => set('stop_gap_min_usdt', v)} />
          <Field label="최대 손절 간격" hint="ATR이 커도 손절 가격 간격은 여기까지만 허용해요" value={form.stop_gap_max_usdt} step="50" min={form.stop_gap_min_usdt} suffix="USDT" onChange={(v) => set('stop_gap_max_usdt', v)} />
          <Field label="1차 익절 최소 간격" hint="1차 익절 가격 간격의 하한이에요" value={form.take_profit_1_min_usdt} step="50" min="1" suffix="USDT" onChange={(v) => set('take_profit_1_min_usdt', v)} />
          <Field label="1차 익절 최대 간격" hint="1차 익절 가격 간격의 상한이에요" value={form.take_profit_1_max_usdt} step="50" min={form.take_profit_1_min_usdt} suffix="USDT" onChange={(v) => set('take_profit_1_max_usdt', v)} />
          <Field label="2차 익절 간격" hint="두 번째 목표가는 진입가에서 이만큼 떨어져 잡아요" value={form.take_profit_2_usdt} step="50" min={form.take_profit_1_max_usdt} suffix="USDT" onChange={(v) => set('take_profit_2_usdt', v)} />
        </SettingGroup>

        <SettingGroup title="진입 조건" note="WAIT 상태에서는 진입하지 않고, 확정 신호만 자동 진입 후보가 돼요">
          <Field
            label="확정 신호 기준"
            hint="현재 전략은 점수 예측이 아니라 WAIT 이후 SHORT/LONG 확정 신호가 나와야 진입해요"
            value={form.confidence_threshold}
            step="5"
            min="0"
            max="100"
            suffix="%"
            onChange={(v) => set('confidence_threshold', v)}
            warn={confidenceWarn}
            warnText="100%를 넘으면 확정 신호도 차단될 수 있어요"
          />
          <Field
            label="재진입 대기"
            hint={`거래가 끝난 뒤 다음 진입까지 쉬는 시간이에요 (${minutesLabel(form.reentry_wait_seconds)})`}
            value={form.reentry_wait_seconds}
            step="60"
            min="0"
            suffix="초"
            onChange={(v) => set('reentry_wait_seconds', Math.trunc(v))}
          />
        </SettingGroup>

        <SettingGroup title="손실 보호" note="설정한 손실 기준에 닿으면 자동매매가 스스로 멈춰요">
          <Field
            label="1회 최대 손실률"
            hint="거래 한 번에서 이 비율 넘게 잃을 것 같으면 그 전에 진입 자체를 막아요"
            value={form.max_loss_pct}
            step="0.5"
            min="0.1"
            suffix="%"
            onChange={(v) => set('max_loss_pct', v)}
          />
          <Field
            label="일일 최대 손실률"
            hint="하루 누적 손실이 이 비율에 도달하면 그날은 자동매매를 완전히 중지해요"
            value={form.daily_max_loss_pct}
            step="1"
            min="0.5"
            suffix="%"
            onChange={(v) => set('daily_max_loss_pct', v)}
            warn={dailyLossWarn}
            warnText="10%가 넘으면 하루 만에 계좌에 큰 타격을 입을 수 있어요"
          />
          <Field
            label="연속 손실 정지"
            hint="손실이 이 횟수만큼 연속으로 나면, 잘못된 흐름으로 보고 잠시 멈춰요"
            value={form.consecutive_loss_limit}
            step="1"
            min="1"
            suffix="회"
            onChange={(v) => set('consecutive_loss_limit', Math.trunc(v))}
          />
        </SettingGroup>

        <SettingGroup title="실거래 안전장치" note="꺼두면 LIVE 모드여도 실제 주문은 나가지 않고 신호만 확인돼요">
          <label className={`switch-row ${form.live_trading_allowed ? 'switch-row--on' : ''}`}>
            <span>
              <strong className="setting-row__main-label">실거래 주문 허용</strong>
              <span className="setting-row__hint">
                {form.live_trading_allowed
                  ? '켜져 있어요 — LIVE 모드에서 실제 돈으로 주문이 나가요'
                  : '꺼져 있어요 — 무슨 모드든 실제 주문은 절대 나가지 않아요'}
              </span>
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
    <div className="group-card">
      <div className="group-card__header">
        <strong>{title}</strong>
        <span>{note}</span>
      </div>
      <div className="stack group-card__body">{children}</div>
    </div>
  )
}

function Field({ label, hint, value, step, min, max, suffix, onChange, warn, warnText }) {
  return (
    <div className={`stat-box setting-row ${warn ? 'setting-row--warn' : ''}`}>
      <label className="setting-row__inner">
        <span>
          <strong className="setting-row__main-label">{label}</strong>
          <span className="setting-row__hint">{hint}</span>
        </span>
        <span className="setting-row__input-group">
          <input type="number" value={value} step={step} min={min} max={max} onChange={(e) => onChange(Number(e.target.value))} />
          {suffix && <span className="setting-row__suffix">{suffix}</span>}
        </span>
      </label>
      {warn && warnText && <div className="setting-row__warn-text">⚠ {warnText}</div>}
    </div>
  )
}
