// 역할: 매매 기록과 손익 내역을 보여주는 화면.
import { TradeLogTable } from '../components/TradeLogTable'

const TIMEFRAME_CARDS = [
  ['5m', '5분'],
  ['15m', '15분'],
  ['30m', '30분'],
  ['1H', '1시간'],
  ['4H', '4시간'],
  ['6H', '6시간'],
  ['1D', '1일'],
]

const DIRECTION_TEXT = {
  LONG: '매수',
  SHORT: '매도',
  HOLD: '관망',
}

const DIRECTION_TONE = {
  LONG: 'tone-long',
  SHORT: 'tone-short',
  HOLD: 'tone-hold',
}

function getDirection(directions, key) {
  return directions?.[key] ?? directions?.[key.toLowerCase()] ?? 'HOLD'
}

function TimeframePositionCards({ directions }) {
  return (
    <div className="timeframe-position-strip">
      {TIMEFRAME_CARDS.map(([key, label]) => {
        const direction = getDirection(directions, key)
        return (
          <div key={key} className={`timeframe-position-pill ${DIRECTION_TONE[direction] ?? 'tone-hold'}`}>
            <span>{label}</span>
            <strong>{DIRECTION_TEXT[direction] ?? '관망'}</strong>
          </div>
        )
      })}
    </div>
  )
}

export function TradeHistory({ trades, signal, pendingEntry, currentPrice }) {
  return (
    <section className="workspace-panel">
      <div className="workspace-panel__top">
        <div>
          <h2>거래 기록</h2>
          <p>LIVE, PAPER 거래 복기</p>
        </div>
        <TimeframePositionCards directions={signal?.timeframe_directions} />
      </div>
      <div className="stack stack--lg">
        <TradeLogTable
          trades={trades}
          signal={signal}
          pendingEntry={pendingEntry}
          currentPrice={currentPrice}
        />
      </div>
    </section>
  )
}
