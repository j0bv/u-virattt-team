from datetime import datetime, timedelta
import os
import matplotlib.pyplot as plt
import pandas as pd

from src.tools import get_price_data
from src.agents import run_hedge_fund
from src.execution import ExecutionClient

class Backtester:
    def __init__(self, agent, ticker, start_date, end_date, initial_capital, 
                 paper_trading=True, network="arbitrum", trailing_stop_percent=None):
        self.agent = agent
        self.ticker = ticker
        self.start_date = start_date
        self.end_date = end_date
        self.initial_capital = initial_capital
        self.portfolio = {"cash": initial_capital, "stock": 0}
        self.portfolio_values = []
        self.executor = ExecutionClient(network=network) if paper_trading is not None else None
        self.trailing_stop_percent = trailing_stop_percent or float(os.getenv("DEFAULT_TRAILING_STOP_PERCENT", 2.0))
        self.trailing_stop_activation_offset = float(os.getenv("TRAILING_STOP_ACTIVATION_OFFSET", 1.0))
        
    def parse_action(self, agent_output):
        try:
            # Expect JSON output from agent
            import json
            decision = json.loads(agent_output)
            return (
                decision["action"],
                decision.get("quantity", 0),
                decision.get("leverage", 1),
                decision.get("trailing_stop_percent", self.trailing_stop_percent),
                decision.get("trailing_stop_activation_offset", self.trailing_stop_activation_offset)
            )
        except:
            print(f"Error parsing action: {agent_output}")
            return "hold", 0, 1, self.trailing_stop_percent, self.trailing_stop_activation_offset

    async def execute_trade(self, action, quantity, current_price, leverage=1, 
                          trailing_stop_percent=None, trailing_stop_activation_offset=None):
        """Execute trades using either paper trading or live trading."""
        if self.executor:
            try:
                order_result = await self.executor.execute_trade(
                    action=action,
                    symbol=self.ticker,
                    amount=quantity * current_price,  # Convert quantity to USD amount
                    leverage=leverage,
                    trailing_stop_percent=trailing_stop_percent,
                    trailing_stop_activation_offset=trailing_stop_activation_offset
                )
                
                if order_result.get("status") == "filled":
                    if action == "buy":
                        self.portfolio["stock"] += quantity
                        self.portfolio["cash"] -= quantity * current_price
                    else:  # sell
                        self.portfolio["stock"] -= quantity
                        self.portfolio["cash"] += quantity * current_price
                    return quantity
                return 0
            except Exception as e:
                print(f"Order execution failed: {str(e)}")
                return 0
        else:
            # Use original paper trading logic
            if action == "buy" and quantity > 0:
                cost = quantity * current_price
                if cost <= self.portfolio["cash"]:
                    self.portfolio["stock"] += quantity
                    self.portfolio["cash"] -= cost
                    return quantity
                else:
                    max_quantity = self.portfolio["cash"] // current_price
                    if max_quantity > 0:
                        self.portfolio["stock"] += max_quantity
                        self.portfolio["cash"] -= max_quantity * current_price
                        return max_quantity
                    return 0
            elif action == "sell" and quantity > 0:
                quantity = min(quantity, self.portfolio["stock"])
                if quantity > 0:
                    self.portfolio["cash"] += quantity * current_price
                    self.portfolio["stock"] -= quantity
                    return quantity
                return 0
            return 0

    async def run_backtest(self):
        dates = pd.date_range(self.start_date, self.end_date, freq="B")

        print("\nStarting backtest...")
        print(f"{'Date':<12} {'Ticker':<6} {'Action':<6} {'Quantity':>8} {'Leverage':>8} {'Price':>8} "
              f"{'Trail%':>7} {'Cash':>12} {'Stock':>8} {'Total Value':>12}")
        print("-" * 90)

        try:
            for current_date in dates:
                lookback_start = (current_date - timedelta(days=30)).strftime("%Y-%m-%d")
                current_date_str = current_date.strftime("%Y-%m-%d")

                agent_output = self.agent(
                    ticker=self.ticker,
                    start_date=lookback_start,
                    end_date=current_date_str,
                    portfolio=self.portfolio
                )

                action, quantity, leverage, trail_percent, trail_activation = self.parse_action(agent_output)
                df = get_price_data(self.ticker, lookback_start, current_date_str)
                current_price = df.iloc[-1]['close']

                # Execute the trade with validation and trailing stop
                executed_quantity = await self.execute_trade(
                    action, quantity, current_price, leverage, 
                    trail_percent, trail_activation
                )

                # Update total portfolio value
                total_value = self.portfolio["cash"] + self.portfolio["stock"] * current_price
                self.portfolio["portfolio_value"] = total_value
                self.portfolio_values.append({
                    "date": current_date,
                    "portfolio_value": total_value,
                    "action": action,
                    "quantity": executed_quantity,
                    "leverage": leverage,
                    "trailing_stop": trail_percent,
                    "price": current_price
                })

                print(f"{current_date_str:<12} {self.ticker:<6} {action:<6} {executed_quantity:>8} {leverage:>8} "
                      f"{current_price:>8.2f} {trail_percent:>7.1f} {self.portfolio['cash']:>12.2f} "
                      f"{self.portfolio['stock']:>8} {total_value:>12.2f}")

        finally:
            # Clean up trailing stop monitoring
            if self.executor:
                await self.executor.stop_price_updates()

    def analyze_performance(self):
        # Convert portfolio values to DataFrame
        performance_df = pd.DataFrame(self.portfolio_values).set_index("date")

        # Calculate total return
        total_return = (
                           self.portfolio["portfolio_value"] - self.initial_capital
                       ) / self.initial_capital
        print(f"Total Return: {total_return * 100:.2f}%")

        # Plot the portfolio value over time
        performance_df["portfolio_value"].plot(
            title="Portfolio Value Over Time", figsize=(12, 6)
        )
        plt.ylabel("Portfolio Value ($)")
        plt.xlabel("Date")
        plt.show()

        # Compute daily returns
        performance_df["Daily Return"] = performance_df["portfolio_value"].pct_change()

        # Calculate Sharpe Ratio (assuming 252 trading days in a year)
        mean_daily_return = performance_df["Daily Return"].mean()
        std_daily_return = performance_df["Daily Return"].std()
        sharpe_ratio = (mean_daily_return / std_daily_return) * (252 ** 0.5)
        print(f"Sharpe Ratio: {sharpe_ratio:.2f}")

        # Calculate Maximum Drawdown
        rolling_max = performance_df["portfolio_value"].cummax()
        drawdown = performance_df["portfolio_value"] / rolling_max - 1
        max_drawdown = drawdown.min()
        print(f"Maximum Drawdown: {max_drawdown * 100:.2f}%")

        return performance_df

### 4. Run the Backtest #####
if __name__ == "__main__":
    import argparse
    import asyncio

    # Set up argument parser
    parser = argparse.ArgumentParser(description='Run backtesting simulation')
    parser.add_argument('--ticker', type=str, help='Stock ticker symbol (e.g., AAPL)')
    parser.add_argument('--end_date', type=str, default=datetime.now().strftime('%Y-%m-%d'), help='End date in YYYY-MM-DD format')
    parser.add_argument('--start_date', type=str, default=(datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d'), help='Start date in YYYY-MM-DD format')
    parser.add_argument('--initial_capital', type=float, default=100000, help='Initial capital amount (default: 100000)')
    parser.add_argument('--paper_trading', type=bool, default=True, help='Use paper trading mode (default: True)')
    parser.add_argument('--network', type=str, default="arbitrum", help='Network to use for execution (default: arbitrum)')
    parser.add_argument('--trailing_stop_percent', type=float, default=None, help='Trailing stop percentage (default: None)')

    args = parser.parse_args()

    # Create an instance of Backtester
    backtester = Backtester(
        agent=run_hedge_fund,
        ticker=args.ticker,
        start_date=args.start_date,
        end_date=args.end_date,
        initial_capital=args.initial_capital,
        paper_trading=args.paper_trading,
        network=args.network,
        trailing_stop_percent=args.trailing_stop_percent
    )

    # Run the backtesting process
    asyncio.run(backtester.run_backtest())
    performance_df = backtester.analyze_performance()
