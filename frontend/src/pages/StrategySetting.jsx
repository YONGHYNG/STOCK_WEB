// 역할: 매매 전략 설정과 조건값을 조정하는 화면.
import { useEffect, useState } from 'react'
import { tradingApi } from '../api/tradingApi'

const DEFAULTS = {
  strategies: [
    { id: 'trend_continuation', name: '추세 지속', description: 'EMA20·VWAP 눌림목에서 기존 추세 방향으로 진입', enabled: true },
    { id: 'rsi_reversal', name: 'RSI 재돌파·재이탈', description: 'RSI 50선 전환과 EMA·VWAP 정렬을 확인해 진입', enabled: true },
    { id: 'volume_breakout', name: '거래량 돌파', description: '거래량과 ADX가 동반된 돌파 및 재테스트에 진입', enabled: true },
    { id: 'range_reversion', name: '횡보장 밴드 반전', description: '낮은 ADX 구간에서 볼린저밴드 반전을 거래', enabled: true },
    { id: 'neutral_momentum', name: '중립장 모멘텀', description: '장세 전환 과정의 강한 단기 모멘텀에 진입', enabled: true },
  ],
  order_size_btc: 0.001,
  max_loss_pct: 1,
  daily_max_loss_pct: 3,
  consecutive_loss_limit: 3,
  auto_stop_loss_analysis: true,
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
  const normalize = (value) => ({ ...DEFAULTS, ...(value ?? {}), strategies: value?.strategies ?? DEFAULTS.strategies })
  const [form, setForm] = useState(normalize(settings))
  const [strategyBusy, setStrategyBusy] = useState(null)
  const [strategyError, setStrategyError] = useState('')

  useEffect(() => {
    if (settings) setForm(normalize(settings))
  }, [settings])

  async function persistStrategies(nextStrategies, actionId) {
    const payload = { ...normalize(settings), strategies: nextStrategies }
    setStrategyBusy(actionId)
    setStrategyError('')
    try {
      await tradingApi.saveRiskSettings(payload)
      setForm((prev) => ({ ...prev, strategies: nextStrategies }))
      onSaved?.(payload)
    } catch (error) {
      setStrategyError(error?.message || '전략 설정을 저장하지 못했습니다.')
    } finally {
      setStrategyBusy(null)
    }
  }

  function toggleStrategy(strategy) {
    const next = form.strategies.map((item) => item.id === strategy.id ? { ...item, enabled: !item.enabled } : item)
    persistStrategies(next, strategy.id)
  }

  function deleteStrategy(strategy) {
    if (!window.confirm(`'${strategy.name}' 전략을 삭제할까요?\n삭제하면 해당 신호로 신규 진입하지 않습니다.`)) return
    persistStrategies(form.strategies.filter((item) => item.id !== strategy.id), strategy.id)
  }

  async function toggleStopLossAnalysis() {
    const next = { ...form, auto_stop_loss_analysis: !form.auto_stop_loss_analysis }
    setStrategyBusy('auto_stop_loss_analysis')
    setStrategyError('')
    try {
      await tradingApi.saveRiskSettings(next)
      setForm(next)
      onSaved?.(next)
    } catch (error) {
      setStrategyError(error?.message || '자동 손절 분석 설정을 저장하지 못했습니다.')
    } finally {
      setStrategyBusy(null)
    }
  }

  return (
    <section className="workspace-panel">
      <div className="workspace-panel__top">
        <div>
          <h2>전략 및 리스크 설정</h2>
          <p>자동매매가 언제, 얼마나, 어디까지 움직일지 여기서 정해요</p>
        </div>
      </div>

      <div className="strategy-registry">
        <div className="strategy-registry__header">
          <div>
            <h3>손절 후 자동 처리</h3>
            <p>손절 마감, 서버 중단 중 누락 복구, 손실 원인 기록을 자동으로 처리합니다.</p>
          </div>
          <span>{form.auto_stop_loss_analysis ? '자동 처리 ON' : '자동 처리 OFF'}</span>
        </div>
        <article className={`strategy-item ${form.auto_stop_loss_analysis ? 'strategy-item--enabled' : ''}`}>
          <div className="strategy-item__copy">
            <strong>자동 손절 분석</strong>
            <p>손절이 나면 다시 요청하지 않아도 시간대 방향과 진입 신호를 분석해 거래 기록에 남겨요.</p>
          </div>
          <div className="strategy-item__actions">
            <button type="button" disabled={strategyBusy === 'auto_stop_loss_analysis'} onClick={toggleStopLossAnalysis}>
              {strategyBusy === 'auto_stop_loss_analysis' ? '저장 중…' : form.auto_stop_loss_analysis ? '끄기' : '켜기'}
            </button>
          </div>
        </article>
      </div>

      <div className="strategy-registry">
        <div className="strategy-registry__header">
          <div>
            <h3>등록된 전략</h3>
            <p>적용 중인 전략만 신규 진입 신호에 사용됩니다.</p>
          </div>
          <span>{form.strategies.filter((item) => item.enabled).length}/{form.strategies.length}개 적용 중</span>
        </div>
        {strategyError && <div className="strategy-registry__error">{strategyError}</div>}
        {form.strategies.length ? (
          <div className="strategy-list">
            {form.strategies.map((strategy) => (
              <article key={strategy.id} className={`strategy-item ${strategy.enabled ? 'strategy-item--enabled' : ''}`}>
                <div className="strategy-item__copy">
                  <div className="strategy-item__title-row">
                    <strong>{strategy.name}</strong>
                    <span className={strategy.enabled ? 'strategy-state strategy-state--on' : 'strategy-state'}>
                      {strategy.enabled ? '적용 중' : '미적용'}
                    </span>
                  </div>
                  <p>{strategy.description}</p>
                </div>
                <div className="strategy-item__actions">
                  <button type="button" disabled={strategyBusy === strategy.id} onClick={() => toggleStrategy(strategy)}>
                    {strategyBusy === strategy.id ? '저장 중…' : strategy.enabled ? '미적용' : '적용'}
                  </button>
                  <button type="button" className="strategy-delete" disabled={strategyBusy === strategy.id} onClick={() => deleteStrategy(strategy)}>
                    삭제
                  </button>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <div className="strategy-registry__empty">등록된 전략이 없습니다.</div>
        )}
      </div>

      <div className="settings-summary">
        <div className="settings-summary__title">지금 설정을 말로 풀면</div>
        <ul className="settings-summary__list">
          <li>확정 진입 신호가 나온 뒤 리스크 검사를 통과할 때만, 최대 <b>{form.max_leverage}배</b> 레버리지로 <b>{form.order_size_btc} BTC</b>씩 자동 진입해요</li>
          <li>한 번에 <b>{form.max_loss_pct}%</b> 넘게 잃거나 하루 합계로 <b>{form.daily_max_loss_pct}%</b> 잃으면 그날은 더 이상 진입하지 않아요</li>
          <li>손실이 <b>{form.consecutive_loss_limit}번</b> 연속되면 잠시 멈추고, 다음 진입까지는 <b>{minutesLabel(form.reentry_wait_seconds)}</b> 기다려요</li>
          <li>손절 후 자동 마감·누락 복구·원인 분석은 <b>{form.auto_stop_loss_analysis ? '켜짐' : '꺼짐'}</b> 상태예요</li>
          <li>진입가 기준 손절 간격은 <b>{form.stop_gap_min_usdt}~{form.stop_gap_max_usdt} USDT</b>, 전량 매도 간격은 <b>{form.take_profit_1_min_usdt}~{form.take_profit_1_max_usdt} USDT</b>, 추가 참고 목표는 <b>{form.take_profit_2_usdt} USDT</b>예요</li>
          <li>실거래 주문은 지금 <b className={form.live_trading_allowed ? 'tone-short' : 'tone-long'}>{form.live_trading_allowed ? '허용됨 (실제 돈이 움직여요)' : '차단됨 (신호만 보여줘요)'}</b></li>
        </ul>
      </div>
    </section>
  )
}
