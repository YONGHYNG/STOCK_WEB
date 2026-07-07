// 역할: 리스크 상태와 보호 조건을 보여주는 화면.
function money(v) {
  return v != null ? `$${Number(v).toLocaleString('en-US', { minimumFractionDigits: 2 })}` : '-'
}

function pct(v) {
  return v != null ? `${(Number(v) * 100).toFixed(3)}%` : '-'
}

export function RiskStatus({ signal }) {
  const direction = signal?.direction ?? 'HOLD'
  const grade = signal?.entry_grade ?? '-'
  const warnings = signal?.risk_warnings ?? []
  const canEnter = direction !== 'HOLD' && !['C', 'D', 'F'].includes(grade) && warnings.length === 0

  const pricePlan = [
    ['손절가', money(signal?.stop_loss), 'var(--red)'],
    ['1차 익절가', money(signal?.take_profit_1), 'var(--green)'],
    ['2차 익절가', money(signal?.take_profit_2), 'var(--green)'],
    ['3차 익절가', money(signal?.take_profit_3), 'var(--green)'],
  ]

  const costPlan = [
    ['순손익비', signal?.net_risk_reward ? `1 : ${signal.net_risk_reward}` : '-', 'var(--yellow)'],
    ['스프레드', pct(signal?.spread_rate), 'var(--text)'],
    ['펀딩비', pct(signal?.funding_rate), 'var(--text)'],
    ['포지션 수량', signal?.position_size_btc ? `${signal.position_size_btc} BTC` : '-', 'var(--text)'],
    ['예상 수수료', signal?.estimated_fee != null ? `$${Number(signal.estimated_fee).toFixed(4)}` : '-', 'var(--text2)'],
    ['청산가', money(signal?.liquidation_price), 'var(--red)'],
  ]

  return (
    <section className="workspace-panel">
      <div className="workspace-panel__top">
        <div>
          <h2>리스크 상태</h2>
          <p>현재 신호가 실제 진입 가능한 자리인지 확인</p>
        </div>
      </div>

      <div style={S.summary}>
        <div style={S.summaryItem}>
          <span style={S.label}>현재 판단</span>
          <strong style={{ ...S.summaryValue, color: direction === 'LONG' ? 'var(--green)' : direction === 'SHORT' ? 'var(--red)' : 'var(--yellow)' }}>{direction}</strong>
        </div>
        <div style={S.summaryItem}>
          <span style={S.label}>진입 등급</span>
          <strong style={S.summaryValue}>{grade}</strong>
        </div>
        <div style={S.summaryItem}>
          <span style={S.label}>자동 진입</span>
          <strong style={{ ...S.summaryValue, color: canEnter ? 'var(--green)' : 'var(--red)' }}>{canEnter ? '가능' : '차단/관망'}</strong>
        </div>
      </div>

      <RiskGroup title="가격 계획" note="진입 후 손절과 분할 익절 기준">
        <MetricGrid items={pricePlan} />
      </RiskGroup>

      <RiskGroup title="비용 및 청산 위험" note="수수료, 펀딩비, 청산가 안전거리 확인">
        <MetricGrid items={costPlan} />
      </RiskGroup>

      <RiskGroup title="위험 경고" note="하나라도 강한 경고가 있으면 자동 진입이 막힘">
        {warnings.length === 0 ? (
          <div style={S.clearBox}>현재 표시된 위험 경고 없음</div>
        ) : (
          <div style={S.warningList}>
            {warnings.map((warning) => <div key={warning} style={S.warning}>{warning}</div>)}
          </div>
        )}
      </RiskGroup>
    </section>
  )
}

function RiskGroup({ title, note, children }) {
  return (
    <div style={S.group}>
      <div style={S.groupHeader}>
        <strong>{title}</strong>
        <span>{note}</span>
      </div>
      {children}
    </div>
  )
}

function MetricGrid({ items }) {
  return (
    <div style={S.grid}>
      {items.map(([label, value, color]) => (
        <div key={label} style={S.card}>
          <div style={S.label}>{label}</div>
          <div style={{ ...S.value, color }}>{value}</div>
        </div>
      ))}
    </div>
  )
}

const S = {
  summary: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 8, marginBottom: 12 },
  summaryItem: { background: 'var(--card)', border: '1px solid var(--border-soft)', borderRadius: 8, padding: '12px 14px' },
  summaryValue: { display: 'block', fontSize: 22, marginTop: 5 },
  group: { border: '1px solid var(--border-soft)', borderRadius: 8, background: 'rgba(255,255,255,0.024)', overflow: 'hidden', marginTop: 12 },
  groupHeader: { display: 'grid', gap: 4, padding: '12px 14px', borderBottom: '1px solid var(--border-soft)', background: 'rgba(101,183,255,0.055)' },
  grid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 8, padding: 10 },
  card: { background: 'var(--card)', border: '1px solid var(--border-soft)', borderRadius: 8, padding: '12px 14px' },
  label: { fontSize: 11, color: 'var(--text2)', marginBottom: 6 },
  value: { fontSize: 17, fontWeight: 850, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' },
  clearBox: { margin: 10, padding: '12px 14px', borderRadius: 8, border: '1px solid rgba(51,209,122,0.28)', color: 'var(--green)', background: 'var(--green-dim)' },
  warningList: { display: 'grid', gap: 8, padding: 10 },
  warning: { padding: '10px 12px', borderRadius: 8, border: '1px solid rgba(255,92,92,0.28)', color: 'var(--red)', background: 'var(--red-dim)' },
}
