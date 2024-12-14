import requests

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
        return response.json()

import os

from datetime import datetime

class OrderExecutor:
    def __init__(self, paper=True):
        """Initialize the OrderExecutor with SDK client."""
        self.client = ExecutionClient()
        
    async def get_account(self):
        """Get account information."""
        return await self.client.get_positions()
    
    async def get_position(self, symbol):
        """Get position information for a specific symbol."""
        try:
            positions = await self.client.get_positions()
            return next((pos for pos in positions if pos["symbol"] == symbol), None)
        except Exception:
            return None
            
    async def execute_order(self, symbol, quantity, side):
        """Execute a market order."""
        # Validate inputs
        if not isinstance(quantity, int) or quantity <= 0:
            raise ValueError("Quantity must be a positive integer")
        if side not in ["buy", "sell"]:
            raise ValueError("Side must be either 'buy' or 'sell'")
            
        # Submit order through SDK client
        try:
            order = await self.client.execute_trade(
                action=side,
                symbol=symbol,
                amount=quantity,
                leverage=1  # Default leverage
            )
            return {
                "order_id": order.get("id"),
                "symbol": symbol,
                "side": side,
                "quantity": quantity,
                "status": order.get("status", "filled")
            }
        except Exception as e:
            raise Exception(f"Order execution failed: {str(e)}")
