export interface TradeRequest {
  action: 'LONG' | 'SHORT' | 'CLOSE';
  symbol: string;
  amount: number;
  leverage: number;
  stopLoss?: number;
  takeProfit?: number;
}

export interface TrailingStopConfig {
  activationPrice?: number;  // Price at which trailing stop becomes active
  trailPercent: number;     // Distance to maintain from price as percentage
  currentStop: number;      // Current stop price
  highWaterMark: number;    // Highest/lowest price since activation
}

export interface PositionSizing {
  riskPercent: number;      // Percentage of account to risk
  accountValue: number;     // Current account value
  maxPositionSize: number;  // Maximum position size allowed
  positionSize: number;     // Calculated position size
  leverage: number;         // Leverage used
}

export interface Position {
  symbol: string;
  size: number;
  leverage: number;
  entryPrice: number;
  liquidationPrice: number;
  unrealizedPnl: number;
  side: 'LONG' | 'SHORT';
  trailingStop?: TrailingStopConfig;
  sizing?: PositionSizing;
}

export interface OrderBook {
  symbol: string;
  bids: [number, number][]; // [price, size][]
  asks: [number, number][]; // [price, size][]
}

export interface TradeUpdate {
  type: 'EXECUTION' | 'POSITION_UPDATE' | 'LIQUIDATION' | 'ERROR';
  data: any;
  timestamp: number;
}
