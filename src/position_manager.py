from dataclasses import dataclass
from typing import Optional, Dict
import asyncio
from decimal import Decimal

@dataclass
class TrailingStop:
    activation_price: Optional[float]  # Price at which trailing stop becomes active
    trail_percent: float               # Distance to maintain from price as percentage
    current_stop: float               # Current stop price
    high_water_mark: float            # Highest/lowest price since activation
    is_active: bool = False           # Whether the trailing stop is currently active

@dataclass
class PositionSize:
    risk_percent: float               # Percentage of account to risk
    account_value: float              # Current account value
    max_position_size: float          # Maximum position size allowed
    position_size: float              # Calculated position size
    leverage: float                   # Leverage used

class PositionManager:
    def __init__(self):
        self.trailing_stops: Dict[str, TrailingStop] = {}
        self.position_sizes: Dict[str, PositionSize] = {}
        
    def calculate_position_size(self, 
                              symbol: str,
                              account_value: float,
                              risk_percent: float,
                              entry_price: float,
                              stop_loss: float,
                              max_leverage: float = 5.0,
                              max_position_percent: float = 0.2) -> PositionSize:
        """
        Calculate position size based on risk management parameters
        
        Args:
            symbol: Trading pair symbol
            account_value: Total account value
            risk_percent: Percentage of account willing to risk (e.g., 0.01 for 1%)
            entry_price: Intended entry price
            stop_loss: Stop loss price
            max_leverage: Maximum allowed leverage
            max_position_percent: Maximum position size as percentage of account
        """
        # Calculate risk amount in currency
        risk_amount = account_value * risk_percent
        
        # Calculate price distance to stop loss
        price_distance = abs(entry_price - stop_loss)
        distance_percent = price_distance / entry_price
        
        # Calculate base position size without leverage
        base_position_size = risk_amount / (price_distance)
        
        # Calculate required leverage
        required_leverage = (base_position_size * entry_price) / (account_value * max_position_percent)
        
        # Adjust leverage to be within limits
        leverage = min(required_leverage, max_leverage)
        
        # Calculate final position size with leverage
        position_size = base_position_size * leverage
        
        # Ensure position size doesn't exceed max allowed
        max_position_size = account_value * max_position_percent * leverage
        position_size = min(position_size, max_position_size)
        
        position_sizing = PositionSize(
            risk_percent=risk_percent,
            account_value=account_value,
            max_position_size=max_position_size,
            position_size=position_size,
            leverage=leverage
        )
        
        self.position_sizes[symbol] = position_sizing
        return position_sizing

    def set_trailing_stop(self,
                         symbol: str,
                         trail_percent: float,
                         current_price: float,
                         activation_price: Optional[float] = None) -> TrailingStop:
        """
        Set up a trailing stop for a position
        
        Args:
            symbol: Trading pair symbol
            trail_percent: Distance to maintain from price as percentage
            current_price: Current market price
            activation_price: Optional price at which trailing stop becomes active
        """
        is_active = activation_price is None or current_price >= activation_price
        
        trailing_stop = TrailingStop(
            activation_price=activation_price,
            trail_percent=trail_percent,
            current_stop=current_price * (1 - trail_percent),
            high_water_mark=current_price,
            is_active=is_active
        )
        
        self.trailing_stops[symbol] = trailing_stop
        return trailing_stop

    def update_trailing_stop(self, symbol: str, current_price: float) -> Optional[TrailingStop]:
        """
        Update trailing stop based on current price
        
        Args:
            symbol: Trading pair symbol
            current_price: Current market price
            
        Returns:
            Updated TrailingStop object if stop is hit, None otherwise
        """
        if symbol not in self.trailing_stops:
            return None
            
        stop = self.trailing_stops[symbol]
        
        # Check if trailing stop should be activated
        if not stop.is_active and stop.activation_price is not None:
            if current_price >= stop.activation_price:
                stop.is_active = True
                stop.high_water_mark = current_price
                stop.current_stop = current_price * (1 - stop.trail_percent)
        
        # Update trailing stop if active
        if stop.is_active:
            # Update high water mark if price is higher
            if current_price > stop.high_water_mark:
                stop.high_water_mark = current_price
                stop.current_stop = current_price * (1 - stop.trail_percent)
            
            # Check if price hit the trailing stop
            if current_price <= stop.current_stop:
                return stop
                
        return None

    def remove_trailing_stop(self, symbol: str):
        """Remove trailing stop for a symbol"""
        if symbol in self.trailing_stops:
            del self.trailing_stops[symbol]

    def get_trailing_stop(self, symbol: str) -> Optional[TrailingStop]:
        """Get trailing stop for a symbol"""
        return self.trailing_stops.get(symbol)

    def get_position_size(self, symbol: str) -> Optional[PositionSize]:
        """Get position size for a symbol"""
        return self.position_sizes.get(symbol)
