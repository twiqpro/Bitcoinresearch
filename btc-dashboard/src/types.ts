export interface EquityPoint {
  date: string;
  strategy: number;
  buy_hold: number;
}

export interface PredictionRow {
  signal_date: string;
  close_t: number;
  pred_next_close: number;
  actual_next_close: number;
}

export interface TradeStint {
  entry_signal_date: string;
  exit_signal_date: string;
  nights_long: number;
  compounded_overnight_gross?: number;
  holding_simple_return_frac?: number;
  stint_profitable_vs_cash_before_fees?: boolean;
}

export interface FeatureImp {
  feature: string;
  importance: number;
}

export interface DeltaCandle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

/** Static bundle from ``export_delta_dashboard.py`` → ``public/delta_perp_candles.json`` */
export interface DeltaPerpPayload {
  generated_at: string;
  resolution: string;
  fetch_hours: number;
  start_unix: number;
  end_unix: number;
  symbols: string[];
  candles: Record<string, DeltaCandle[]>;
}

export interface DashboardPayload {
  generated_at: string;
  fee: number;
  model_mode: string;
  metrics: {
    total_return_strategy_pct: number;
    total_return_bh_pct: number;
    sharpe_strategy: number | null;
    sharpe_bh: number | null;
    max_dd_strategy_pct: number;
    max_dd_bh_pct: number;
    win_rate_stints_pct: number | null;
    n_stints: number;
    n_overnight_rows: number;
  };
  equity_curve: EquityPoint[];
  predictions: PredictionRow[];
  trade_stints: TradeStint[];
  feature_importance: FeatureImp[];
}
