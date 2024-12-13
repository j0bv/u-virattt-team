import requests
import websockets
import json

class ExecutionClient:
    def __init__(self, base_url="http://localhost:3000"):
        self.base_url = base_url
        
    async def execute_trade(self, action, symbol, amount, leverage):
        response = requests.post(f"{self.base_url}/execute", json={
            "action": action,
            "symbol": symbol,
            "amount": amount,
            "leverage": leverage
        })
        return response.json()
        
    async def get_positions(self):
        response = requests.get(f"{self.base_url}/positions")
        return response.json()import os
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from datetime import datetime

class OrderExecutor:
    def __init__(self, paper=True):
        """Initialize the OrderExecutor with Alpaca API credentials."""
        self.api_key = os.environ.get("ALPACA_API_KEY")
        self.api_secret = os.environ.get("ALPACA_API_SECRET")
        
        if not self.api_key or not self.api_secret:
            raise ValueError("Alpaca API credentials not found in environment variables")
        
        self.trading_client = TradingClient(self.api_key, self.api_secret, paper=paper)
        self.data_client = StockHistoricalDataClient(self.api_key, self.api_secret)
        
    def get_account(self):
        """Get account information."""
        return self.trading_client.get_account()
    
    def get_position(self, symbol):
        """Get position information for a specific symbol."""
        try:
            return self.trading_client.get_open_position(symbol)
        except Exception:
            return None
            
    def execute_order(self, symbol, quantity, side):
        """Execute a market order."""
        # Validate inputs
        if not isinstance(quantity, int) or quantity <= 0:
            raise ValueError("Quantity must be a positive integer")
        if side not in ["buy", "sell"]:
            raise ValueError("Side must be either 'buy' or 'sell'")
            
        # Convert side to Alpaca enum
        order_side = OrderSide.BUY if side == "buy" else OrderSide.SELL
        
        # Create order request
        order_request = MarketOrderRequest(
            symbol=symbol,
            qty=quantity,
            side=order_side,
            time_in_force=TimeInForce.DAY
        )
        
        # Submit order
        try:
            order = self.trading_client.submit_order(order_request)
            return {
                "order_id": order.id,
                "symbol": order.symbol,
                "side": side,
                "quantity": quantity,
                "status": order.status
            }
        except Exception as e:
            raise Exception(f"Order execution failed: {str(e)}")
            
    def get_order_status(self, order_id):
        """Get the status of a specific order."""
        return self.trading_client.get_order_by_id(order_id)
        
    def get_historical_data(self, symbol, start_date, end_date):
        """Get historical price data."""
        request = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=TimeFrame.Day,
            start=datetime.strptime(start_date, "%Y-%m-%d"),
            end=datetime.strptime(end_date, "%Y-%m-%d")
        )
        return self.data_client.get_stock_bars(request)
