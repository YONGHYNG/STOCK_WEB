export interface SignalData {
  timestamp: number;
  entry_price: number;
  direction: 'LONG' | 'SHORT' | 'HOLD';
  long_probability: number;
  short_probability: number;
  confidence: number;
  stop_loss: number | null;
  take_profit_1: number | null;
  take_profit_2: number | null;
  take_profit_3?: number | null;
  risk_reward_ratio: number | null;
  all_time_high_mode: boolean;
  all_time_low_mode: boolean;
  timeframe_directions: Record<string, string>;
  reasons: string[];
  analysis_price?: number;
  last_price?: number | null;
  mark_price?: number | null;
  index_price?: number | null;
  best_bid?: number | null;
  best_ask?: number | null;
  expected_entry_long?: number | null;
  expected_entry_short?: number | null;
  long_score?: number;
  short_score?: number;
  entry_grade?: string;
  risk_warnings?: string[];
  spread_rate?: number | null;
  funding_rate?: number | null;
  estimated_fee?: number | null;
  estimated_funding_fee?: number | null;
  net_risk_reward?: number | null;
  position_size_btc?: number | null;
  position_value?: number | null;
  max_loss_usdt?: number | null;
  leverage?: number;
  liquidation_price?: number | null;
  liquidation_gap?: number | null;
  stop_gap?: number | null;
}

export interface AccountInfo {
  accountEquity?: number | string;
  equity?: number | string;
  available?: number | string;
  crossMaxAvailable?: number | string;
  unrealizedPL?: number | string;
}

export interface Position {
  symbol: string;
  holdSide: string;
  total?: number | string;
  available?: number | string;
  unrealizedPL?: number | string;
  leverage?: number | string;
  averageOpenPrice?: number | string;
}

export interface Trade {
  id: number;
  trade_type: string;
  entry_time: string;
  direction: string;
  entry_price: number | null;
  stop_loss: number | null;
  take_profit_1: number | null;
  take_profit_2: number | null;
  exit_price: number | null;
  result: string | null;
  pnl_pct: number | null;
  entry_reason: string | null;
  profit_reason: string | null;
  loss_reason: string | null;
}

export interface AppStatus {
  trading_mode: string;
  auto_trade_enabled: boolean;
  emergency_stopped: boolean;
  demo_mode: boolean;
  seeded: boolean;
  last_price: number | null;
  confidence_threshold: number;
  order_size_btc: number;
}

export interface RiskSettings {
  order_size_btc: number;
  max_loss_pct: number;
  daily_max_loss_pct: number;
  consecutive_loss_limit: number;
  confidence_threshold: number;
  reentry_wait_seconds: number;
  max_leverage: number;
  live_trading_allowed: boolean;
}

export type WsMessage =
  | { type: 'signal'; data: SignalData }
  | { type: 'price'; data: { price: number } }
  | { type: 'log'; data: { message: string } }
  | { type: 'account'; data: { account: AccountInfo; positions: Position[] } }
  | { type: 'trade_update' }
  | { type: 'status'; data: Partial<AppStatus> };
