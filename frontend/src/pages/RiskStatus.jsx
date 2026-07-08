// 역할: 시장가 진입 상황(실제 보유 포지션 또는 진입 시뮬레이션)과 보호 조건을 보여주는 화면.
function money(v) {
  return v != null ? `$${Number(v).toLocaleString('en-US', { minimumFractionDigits: 2 })}` : '-'
}

function pct(v) {
  return v != null ? `${(Number(v) * 100).toFixed(3)}%` : '-'
}

function num(v) {
  const n = Number(v)
  return Number.isFinite(n) && v != null && v !== '' ? n : null
}

export function RiskStatus({ signal, account, positions }) {
  const btcPosition = (positions ?? []).find((p) => p.symbol === 'BTCUSDT' && Number(p.total ?? 0) > 0)

  return btcPosition
    ? <OpenPositionRisk position={btcPosition} signal={signal} />
    : <PlannedEntryRisk signal={signal} />
}

// 실제로 보유 중인 포지션이 있을 때: 거래소가 알려주는 진짜 숫자를 그대로 보여줌
function OpenPositionRisk({ position, signal }) {
  const direction = (position.holdSide ?? '').toUpperCase()
  const size = num(position.total)
  const leverage = num(position.leverage)
  const entry = num(position.openPriceAvg)
  const mark = num(position.markPrice) ?? num(signal?.mark_price) ?? num(signal?.last_price)
  const liq = num(position.liquidationPrice)
  const pnl = num(position.unrealizedPL) ?? 0
  const margin = num(position.marginSize) ?? (entry && leverage && size ? (entry * size) / leverage : null)
  const pnlPct = margin ? (pnl / margin) * 100 : null
  const liqBuffer = mark && liq ? Math.abs(mark - liq) / mark : null
  const warnings = signal?.risk_warnings ?? []

  const danger = liqBuffer != null && liqBuffer < 0.1
  const losing = pnl < 0
  const heroTone = danger ? 'risk-hero--danger' : losing ? 'risk-hero--warn' : 'risk-hero--ok'

  const positionMetrics = [
    ['평균 진입가', money(entry), '', '이 포지션을 처음 잡았을 때 평균적으로 체결된 가격이에요'],
    ['현재가(마크가)', money(mark), '', '지금 이 순간 손익 계산의 기준이 되는 실시간 가격이에요'],
    ['레버리지', leverage != null ? `${leverage}배` : '-', '', '원금 대비 몇 배로 베팅했는지예요. 높을수록 청산 위험도 커요'],
    ['보유 수량', size != null ? `${size} BTC` : '-', '', '지금 실제로 들고 있는 BTC 수량이에요'],
    ['사용 증거금', margin != null ? money(margin) : '-', 'tone-muted', '이 포지션을 유지하려고 실제로 묶여 있는 내 돈이에요'],
    ['청산가', money(liq), 'tone-short', '이 가격에 닿으면 포지션이 강제로 종료되고 손실이 확정돼요'],
  ]

  return (
    <section className="workspace-panel">
      <div className="workspace-panel__top">
        <div>
          <h2>시장가 진입 상황 · 보유 중</h2>
          <p>지금 실제로 들고 있는 포지션을 거래소 기준 실시간 값으로 보여줘요</p>
        </div>
      </div>

      <div className={`risk-hero ${heroTone}`}>
        <div className={`risk-hero__badge ${direction === 'SHORT' ? 'tone-short' : 'tone-long'}`}>
          {direction === 'SHORT' ? '하락(SHORT)' : '상승(LONG)'} 포지션 보유 중 · {size ?? '-'} BTC
        </div>
        <div className="risk-hero__sub">
          <div>
            미실현 손익 <strong className={pnl >= 0 ? 'tone-long' : 'tone-short'}>
              {pnl >= 0 ? '+' : ''}{money(pnl)}{pnlPct != null ? ` (${pnlPct >= 0 ? '+' : ''}${pnlPct.toFixed(1)}%)` : ''}
            </strong>
            {' '}— 지금 청산하면 실제로 얻거나 잃는 금액이에요
          </div>
          {danger && <div>· 청산가까지 {(liqBuffer * 100).toFixed(1)}%밖에 안 남았어요 — 급락/급등에 취약해요</div>}
        </div>
      </div>

      <RiskGroup title="포지션 상세" note="거래소가 실시간으로 알려주는 실제 보유 정보">
        <MetricGrid items={positionMetrics} />
        {liqBuffer != null && (
          <div className="buffer-note">
            현재가에서 청산가까지 <strong className={danger ? 'tone-short' : ''}>{(liqBuffer * 100).toFixed(1)}%</strong> 여유가 있어요
            {danger ? ' — 여유가 적어 위험해요' : ' — 아직은 안전한 편이에요'}
          </div>
        )}
      </RiskGroup>

      <RiskGroup title="보유 중 위험 경고" note="포지션을 유지하는 동안에도 계속 감시하는 시장 위험">
        {warnings.length === 0 ? (
          <div className="clear-card">현재 표시된 위험 경고 없음</div>
        ) : (
          <div className="warning-list">
            {warnings.map((warning) => <div key={warning} className="warning-card">{warning}</div>)}
          </div>
        )}
      </RiskGroup>
    </section>
  )
}

// 보유 중인 포지션이 없을 때: 다음 신호가 뜨면 적용될 예정 진입 계획(아직 실제 돈은 안 걸린 상태)
function PlannedEntryRisk({ signal }) {
  const direction = signal?.direction ?? 'HOLD'
  const summary = signal?.timeframe_summary?.['1m'] ?? signal?.timeframe_summary?.['5m'] ?? {}
  const plannedDirection = signal?.planned_direction ?? summary?.plan_direction ?? direction
  const displayDirection = direction === 'HOLD' && plannedDirection !== 'HOLD' ? `WAIT_${plannedDirection}` : direction
  const grade = signal?.entry_grade ?? '-'
  const warnings = signal?.risk_warnings ?? []
  const canEnter = direction !== 'HOLD' && !['C', 'D', 'F'].includes(grade) && warnings.length === 0

  const judgmentTone = plannedDirection === 'LONG' ? 'tone-long' : plannedDirection === 'SHORT' ? 'tone-short' : 'tone-hold'

  const pricePlan = [
    ['손절가', money(signal?.stop_loss), 'tone-short'],
    ['1차 익절가', money(signal?.take_profit_1), 'tone-long'],
    ['2차 익절가', money(signal?.take_profit_2), 'tone-long'],
    ['3차 익절가', money(signal?.take_profit_3), 'tone-long'],
  ]

  const costPlan = [
    ['순손익비', signal?.net_risk_reward ? `1 : ${signal.net_risk_reward}` : '-', 'tone-hold', '위험 1 대비 기대 보상 배수예요. 숫자가 클수록 잃을 위험보다 벌 수 있는 금액이 커요'],
    ['스프레드', pct(signal?.spread_rate), '', '사려는 가격과 팔려는 가격의 차이예요. 클수록 사고팔 때 손해가 더 생겨요'],
    ['펀딩비', pct(signal?.funding_rate), '', '포지션을 계속 들고 있는 동안 주기적으로 내거나 받는 비용이에요'],
    ['포지션 수량', signal?.position_size_btc ? `${signal.position_size_btc} BTC` : '-', '', '이번 거래에서 실제로 사고파는 BTC 수량이에요'],
    ['예상 수수료', signal?.estimated_fee != null ? `$${Number(signal.estimated_fee).toFixed(4)}` : '-', 'tone-muted', '주문이 체결될 때 거래소에 내야 하는 수수료 예상치예요'],
    ['청산가', money(signal?.liquidation_price), 'tone-short', '이 가격에 닿으면 포지션이 강제로 종료되고 손실이 확정돼요'],
  ]

  return (
    <section className="workspace-panel">
      <div className="workspace-panel__top">
        <div>
          <h2>시장가 진입 상황 · 진입 시뮬레이션</h2>
          <p>지금은 보유 중인 포지션이 없어요 — 아래는 신호가 뜨면 적용될 예정 진입 계획이에요</p>
        </div>
      </div>

      <div className="note-box">
        포지션을 잡기 전이라 아직 실제 돈은 걸려 있지 않아요. 아래 숫자는 시세가 바뀔 때마다 AI가 다시 계산한 "만약 지금 진입한다면"의 예상치라서 새로고침마다 조금씩 바뀌는 게 정상이에요.
      </div>

      <div className="grid-auto mini-summary" style={{ '--min-col': '170px' }}>
        <div className="stat-box">
          <span className="eyebrow">현재 판단</span>
          <strong className={`mini-summary__value ${judgmentTone}`}>
            {displayDirection === 'LONG' ? '상승(매수)' : displayDirection === 'SHORT' ? '하락(매도)' : displayDirection === 'WAIT_LONG' ? '대기 롱' : displayDirection === 'WAIT_SHORT' ? '대기 숏' : '관망(대기)'}
          </strong>
          <span className="mini-summary__hint">WAIT는 아직 주문하지 않고, 표시된 예상 진입가까지 온 뒤 확인 캔들이 나올 때만 진입한다는 뜻이에요</span>
        </div>
        <div className="stat-box">
          <span className="eyebrow">진입 등급</span>
          <strong className="mini-summary__value">{grade}</strong>
          <span className="mini-summary__hint">A~B는 진입 가능, C~D~F는 조건이 나빠 자동 진입이 막혀요</span>
        </div>
        <div className="stat-box">
          <span className="eyebrow">자동 진입</span>
          <strong className={`mini-summary__value ${canEnter ? 'tone-long' : 'tone-short'}`}>{canEnter ? '가능' : '차단/관망'}</strong>
          <span className="mini-summary__hint">방향·등급·아래 위험 경고를 모두 통과해야 자동매매가 실제로 진입해요</span>
        </div>
      </div>

      <RiskGroup title="예정 가격 계획" note="실제 진입이 일어나면 적용될 손절과 분할 익절 기준">
        <MetricGrid items={pricePlan} />
      </RiskGroup>

      <RiskGroup title="예정 비용 및 청산 위험" note="실제 진입 시 예상되는 수수료, 펀딩비, 청산가">
        <MetricGrid items={costPlan} />
      </RiskGroup>

      <RiskGroup title="위험 경고" note="하나라도 강한 경고가 있으면 자동 진입이 막힘">
        {warnings.length === 0 ? (
          <div className="clear-card">현재 표시된 위험 경고 없음</div>
        ) : (
          <div className="warning-list">
            {warnings.map((warning) => <div key={warning} className="warning-card">{warning}</div>)}
          </div>
        )}
      </RiskGroup>
    </section>
  )
}

function RiskGroup({ title, note, children }) {
  return (
    <div className="group-card">
      <div className="group-card__header">
        <strong>{title}</strong>
        <span>{note}</span>
      </div>
      {children}
    </div>
  )
}

function MetricGrid({ items }) {
  return (
    <div className="grid-auto group-card__body" style={{ '--min-col': '170px' }}>
      {items.map(([label, value, tone, hint]) => (
        <div key={label} className="stat-box">
          <div className="eyebrow">{label}</div>
          <div className={`stat-value ${tone ?? ''}`}>{value}</div>
          {hint && <div className="hint-text">{hint}</div>}
        </div>
      ))}
    </div>
  )
}
