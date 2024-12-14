import os
import json
import asyncio
import aiohttp
from typing import Dict, Any, Optional
from dataclasses import dataclass
from decimal import Decimal

@dataclass
class TrailingStop:
    symbol: str
    trail_percent: float
    activation_price: Optional[float]
    current_stop: float
    is_active: bool
    side: str  # 'long' or 'short'

class ExecutionClient:
    def __init__(self, base_url: str = "http://localhost:3000", network: str = None):
        """Initialize the Gains Trade execution client with trailing stop support."""
        self.base_url = base_url
        self.network = network or os.getenv("NETWORK", "arbitrum")
        self.trailing_stops: Dict[str, TrailingStop] = {}
        self._price_update_task = None
        self._stop_price_updates = asyncio.Event()
        
    async def start_price_updates(self):
        """Start the price update loop for trailing stops."""
        if self._price_update_task is None:
            self._stop_price_updates.clear()
            self._price_update_task = asyncio.create_task(self._update_trailing_stops())
    
    async def stop_price_updates(self):
        """Stop the price update loop."""
        if self._price_update_task is not None:
            self._stop_price_updates.set()
            await self._price_update_task
            self._price_update_task = None
    
    async def _update_trailing_stops(self):
        """Update trailing stops based on current prices."""
        while not self._stop_price_updates.is_set():
            try:
                for symbol, stop in list(self.trailing_stops.items()):
                    current_price = await self.get_market_price(symbol)
                    
                    # Check if trailing stop should be activated
                    if not stop.is_active and stop.activation_price is not None:
                        if (stop.side == 'long' and current_price >= stop.activation_price) or \
                           (stop.side == 'short' and current_price <= stop.activation_price):
                            stop.is_active = True
                            stop.current_stop = self._calculate_stop_price(current_price, stop)
                    
                    # Update trailing stop if active
                    if stop.is_active:
                        new_stop = self._calculate_stop_price(current_price, stop)
                        if stop.side == 'long':
                            if new_stop > stop.current_stop:
                                stop.current_stop = new_stop
                            elif current_price <= stop.current_stop:
                                await self._execute_stop(symbol, stop)
                        else:  # short
                            if new_stop < stop.current_stop:
                                stop.current_stop = new_stop
                            elif current_price >= stop.current_stop:
                                await self._execute_stop(symbol, stop)
                
            except Exception as e:
                print(f"Error updating trailing stops: {e}")
            
            await asyncio.sleep(1)  # Update every second
    
    def _calculate_stop_price(self, current_price: float, stop: TrailingStop) -> float:
        """Calculate new stop price based on current price and trail percentage."""
        if stop.side == 'long':
            return current_price * (1 - stop.trail_percent / 100)
        else:  # short
            return current_price * (1 + stop.trail_percent / 100)
    
    async def _execute_stop(self, symbol: str, stop: TrailingStop):
        """Execute the trailing stop order."""
        try:
            position = await self.get_position(symbol)
            if position:
                await self.execute_trade(
                    action="sell" if stop.side == 'long' else "buy",
                    symbol=symbol,
                    amount=abs(float(position.get("size", 0))),
                    leverage=float(position.get("leverage", 1))
                )
            del self.trailing_stops[symbol]
        except Exception as e:
            print(f"Error executing stop: {e}")
    
    async def set_trailing_stop(self, symbol: str, trail_percent: float, side: str, 
                              activation_offset: Optional[float] = None):
        """Set a trailing stop for a position."""
        current_price = await self.get_market_price(symbol)
        
        activation_price = None
        if activation_offset is not None:
            offset_multiplier = 1 + (activation_offset / 100)
            activation_price = current_price * offset_multiplier if side == 'long' else current_price / offset_multiplier
        
        self.trailing_stops[symbol] = TrailingStop(
            symbol=symbol,
            trail_percent=trail_percent,
            activation_price=activation_price,
            current_stop=self._calculate_stop_price(current_price, TrailingStop(
                symbol=symbol, trail_percent=trail_percent, activation_price=None,
                current_stop=0, is_active=True, side=side
            )),
            is_active=activation_price is None,
            side=side
        )
        
        await self.start_price_updates()
    
    async def remove_trailing_stop(self, symbol: str):
        """Remove trailing stop for a symbol."""
        if symbol in self.trailing_stops:
            del self.trailing_stops[symbol]
            
        if not self.trailing_stops:
            await self.stop_price_updates()
    
    async def execute_trade(self, action: str, symbol: str, amount: float, leverage: int = 1,
                          trailing_stop_percent: Optional[float] = None,
                          trailing_stop_activation_offset: Optional[float] = None) -> Dict[str, Any]:
        """Execute a trade on Gains Trade with optional trailing stop."""
        async with aiohttp.ClientSession() as session:
            try:
                payload = {
                    "action": action,
                    "symbol": symbol,
                    "amount": amount,
                    "leverage": leverage,
                    "network": self.network
                }
                
                async with session.post(f"{self.base_url}/execute", json=payload) as response:
                    if response.status == 200:
                        result = await response.json()
                        
                        # Set trailing stop if requested
                        if trailing_stop_percent is not None and result.get("status") == "filled":
                            await self.set_trailing_stop(
                                symbol=symbol,
                                trail_percent=trailing_stop_percent,
                                side="long" if action == "buy" else "short",
                                activation_offset=trailing_stop_activation_offset
                            )
                        
                        return result
                    else:
                        error_text = await response.text()
                        raise Exception(f"Trade execution failed: {error_text}")
            except Exception as e:
                raise Exception(f"Failed to execute trade: {str(e)}")
    
    async def get_market_price(self, symbol: str) -> float:
        """Get current market price for a symbol."""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.base_url}/market/{symbol}/price") as response:
                if response.status == 200:
                    data = await response.json()
                    return float(data["price"])
                else:
                    raise Exception("Failed to get market price")
    
    async def get_positions(self) -> Dict[str, Any]:
        """Get current open positions."""
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(f"{self.base_url}/positions", params={"network": self.network}) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        error_text = await response.text()
                        raise Exception(f"Failed to get positions: {error_text}")
            except Exception as e:
                raise Exception(f"Failed to get positions: {str(e)}")
    
    async def get_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get position for a specific symbol."""
        positions = await self.get_positions()
        return next((pos for pos in positions.get("positions", []) 
                    if pos.get("symbol") == symbol), None)
    
    async def get_market_info(self, symbol: str) -> Dict[str, Any]:
        """Get market information for a symbol."""
        async with aiohttp.ClientSession() as session:
            try:
                params = {"network": self.network}
                async with session.get(f"{self.base_url}/market/{symbol}", params=params) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        error_text = await response.text()
                        raise Exception(f"Failed to get market info: {error_text}")
            except Exception as e:
                raise Exception(f"Failed to get market info: {str(e)}")
    
    async def get_account(self) -> Dict[str, Any]:
        """Get account information including balances."""
        async with aiohttp.ClientSession() as session:
            try:
                params = {"network": self.network}
                async with session.get(f"{self.base_url}/account", params=params) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        error_text = await response.text()
                        raise Exception(f"Failed to get account info: {error_text}")
            except Exception as e:
                raise Exception(f"Failed to get account info: {str(e)}")

# Example usage:
async def main():
    # Initialize client with specific network
    client = ExecutionClient(network="polygon")  # or "arbitrum"
    
    # Example trade execution with trailing stop
    result = await client.execute_trade(
        action="buy",
        symbol="BTC/USD",
        amount=1000,
        leverage=2,
        trailing_stop_percent=2.0,  # 2% trailing stop
        trailing_stop_activation_offset=1.0  # Activate when price moves 1% in profit
    )
    print(f"Trade result: {result}")
    
    # Get current positions
    positions = await client.get_positions()
    print(f"Positions: {positions}")
    
    # Get market information
    market_info = await client.get_market_info("BTC/USD")
    print(f"Market info: {market_info}")
    
    # Get account information
    account_info = await client.get_account()
    print(f"Account info: {account_info}")
    
    # Wait for some time to see trailing stop in action
    await asyncio.sleep(60)
    
    # Clean up
    await client.stop_price_updates()

if __name__ == "__main__":
    asyncio.run(main())
