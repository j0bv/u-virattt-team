import asyncio
import json
import websockets
import requests
from dataclasses import dataclass
from typing import Optional, List, Dict, Tuple
from enum import Enum
from position_manager import PositionManager, TrailingStop, PositionSize

class TradeAction(Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    CLOSE = "CLOSE"

@dataclass
class Position:
    symbol: str
    size: float
    leverage: float
    entry_price: float
    liquidation_price: float
    unrealized_pnl: float
    side: str

@dataclass
class OrderBook:
    symbol: str
    bids: List[Tuple[float, float]]  # List of (price, size)
    asks: List[Tuple[float, float]]  # List of (price, size)

class ExecutionClient:
    def __init__(self, base_url="http://localhost:3000"):
        self.base_url = base_url
        self.ws_url = f"ws://{base_url.split('://')[-1]}/ws"
        self.ws = None
        self.callback = None
        self.position_manager = PositionManager()
        self._price_update_task = None
        
    async def connect(self, callback=None):
        """Connect to WebSocket and set up callback for trade updates"""
        self.callback = callback
        self.ws = await websockets.connect(self.ws_url)
        self._price_update_task = asyncio.create_task(self._price_updates())
        asyncio.create_task(self._listen())
    
    async def _price_updates(self):
        """Periodically fetch prices and update trailing stops"""
        while True:
            try:
                for symbol in self.position_manager.trailing_stops.keys():
                    price = await self.get_price(symbol)
                    stop_hit = self.position_manager.update_trailing_stop(symbol, price)
                    
                    if stop_hit:
                        # Execute trailing stop order
                        await self.execute_trade(
                            action=TradeAction.CLOSE,
                            symbol=symbol,
                            amount=0,  # Close entire position
                            leverage=1
                        )
                        
                        # Notify through callback
                        if self.callback:
                            await self.callback({
                                "type": "TRAILING_STOP_HIT",
                                "data": {
                                    "symbol": symbol,
                                    "price": price,
                                    "stop": stop_hit
                                }
                            })
                
            except Exception as e:
                print(f"Error updating prices: {e}")
            
            await asyncio.sleep(1)  # Update every second
    
    async def _listen(self):
        """Listen for WebSocket messages"""
        try:
            while True:
                message = await self.ws.recv()
                data = json.loads(message)
                if self.callback:
                    await self.callback(data)
        except websockets.exceptions.ConnectionClosed:
            print("WebSocket connection closed")
    
    async def execute_trade(self, action: TradeAction, symbol: str, amount: float, 
                          leverage: float, stop_loss: Optional[float] = None, 
                          take_profit: Optional[float] = None) -> dict:
        """Execute a trade with optional stop loss and take profit"""
        response = requests.post(f"{self.base_url}/execute", json={
            "action": action.value,
            "symbol": symbol,
            "amount": amount,
            "leverage": leverage,
            "stopLoss": stop_loss,
            "takeProfit": take_profit
        })
        return response.json()
    
    async def execute_trade_with_risk(self, 
                                    action: TradeAction,
                                    symbol: str,
                                    risk_percent: float,
                                    entry_price: float,
                                    stop_loss: float,
                                    account_value: float,
                                    trail_percent: Optional[float] = None,
                                    activation_price: Optional[float] = None,
                                    max_leverage: float = 5.0) -> dict:
        """
        Execute a trade with position sizing and optional trailing stop
        
        Args:
            action: Trade action (LONG/SHORT)
            symbol: Trading pair symbol
            risk_percent: Percentage of account to risk
            entry_price: Intended entry price
            stop_loss: Initial stop loss price
            account_value: Current account value
            trail_percent: Optional trailing stop percentage
            activation_price: Optional price to activate trailing stop
            max_leverage: Maximum allowed leverage
        """
        # Calculate position size
        position = self.position_manager.calculate_position_size(
            symbol=symbol,
            account_value=account_value,
            risk_percent=risk_percent,
            entry_price=entry_price,
            stop_loss=stop_loss,
            max_leverage=max_leverage
        )
        
        # Execute the trade
        result = await self.execute_trade(
            action=action,
            symbol=symbol,
            amount=position.position_size,
            leverage=position.leverage,
            stop_loss=stop_loss
        )
        
        # Set up trailing stop if requested
        if trail_percent is not None:
            self.position_manager.set_trailing_stop(
                symbol=symbol,
                trail_percent=trail_percent,
                current_price=entry_price,
                activation_price=activation_price
            )
        
        return {
            "trade_result": result,
            "position_size": position,
            "trailing_stop": self.position_manager.get_trailing_stop(symbol)
        }
    
    async def update_trailing_stop(self, 
                                 symbol: str,
                                 trail_percent: Optional[float] = None,
                                 activation_price: Optional[float] = None):
        """Update trailing stop parameters for a position"""
        current_price = await self.get_price(symbol)
        
        if trail_percent is not None:
            self.position_manager.set_trailing_stop(
                symbol=symbol,
                trail_percent=trail_percent,
                current_price=current_price,
                activation_price=activation_price
            )
        
        return self.position_manager.get_trailing_stop(symbol)
    
    async def remove_trailing_stop(self, symbol: str):
        """Remove trailing stop for a position"""
        self.position_manager.remove_trailing_stop(symbol)
    
    async def get_positions(self) -> List[Position]:
        """Get current positions"""
        response = requests.get(f"{self.base_url}/positions")
        data = response.json()
        return [Position(**pos) for pos in data.get("positions", [])]
    
    async def get_orderbook(self, symbol: str) -> OrderBook:
        """Get order book for a symbol"""
        response = requests.get(f"{self.base_url}/orderbook/{symbol}")
        data = response.json()["orderBook"]
        return OrderBook(
            symbol=data["symbol"],
            bids=data["bids"],
            asks=data["asks"]
        )
    
    async def get_price(self, symbol: str) -> float:
        """Get current price for a symbol"""
        response = requests.get(f"{self.base_url}/price/{symbol}")
        return response.json()["price"]
    
    async def close(self):
        """Close WebSocket connection and cleanup"""
        if self._price_update_task:
            self._price_update_task.cancel()
        if self.ws:
            await self.ws.close()

# Example usage:
async def handle_updates(update):
    """Handle real-time updates from the execution service"""
    if update["type"] == "TRAILING_STOP_HIT":
        print(f"Trailing stop hit: {update['data']}")
    elif update["type"] == "EXECUTION":
        print(f"Trade executed: {update['data']}")
    elif update["type"] == "POSITION_UPDATE":
        print(f"Position updated: {update['data']}")
    elif update["type"] == "ERROR":
        print(f"Error: {update['data']['message']}")

async def main():
    client = ExecutionClient()
    await client.connect(callback=handle_updates)
    
    # Example trade with risk management and trailing stop
    result = await client.execute_trade_with_risk(
        action=TradeAction.LONG,
        symbol="ETH-USD",
        risk_percent=0.01,  # Risk 1% of account
        entry_price=2000,
        stop_loss=1900,
        account_value=100000,
        trail_percent=0.02,  # 2% trailing stop
        activation_price=2100  # Activate trailing stop at $2100
    )
    print(f"Trade result: {result}")
    
    await asyncio.sleep(60)  # Let trailing stop monitor run
    await client.close()

if __name__ == "__main__":
    asyncio.run(main())
