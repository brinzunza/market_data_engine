"""
Geometric Brownian Motion (GBM) Generator

Implements the stochastic differential equation:
dS_t = μ * S_t * dt + σ * S_t * dW_t

Where:
- S_t: Asset price at time t
- μ (drift): Expected rate of return
- σ (volatility): Degree of randomness
- dW_t: Wiener process (random shock)
"""

import numpy as np
import time


class GBMGenerator:
    def __init__(self, ticker, start_price, drift, volatility, dt=0.0001, min_price=1, max_price=10000):
        self.ticker = ticker
        self.current_price = start_price
        self.drift = drift  # μ (mu)
        self.volatility = volatility  # σ (sigma)
        self.dt = dt  # Time step (smaller = more granular)
        self.min_price = min_price
        self.max_price = max_price

    def generate_next_price(self):
        """
        Generate the next price point using GBM
        Returns the new price
        """
        # Generate random normal distribution value
        random_shock = np.random.normal(0, 1)

        # Calculate price change using GBM formula
        drift_term = self.drift * self.current_price * self.dt
        diffusion_term = self.volatility * self.current_price * np.sqrt(self.dt) * random_shock

        # Update price
        new_price = self.current_price + drift_term + diffusion_term

        # Apply bounds
        new_price = max(self.min_price, min(self.max_price, new_price))

        self.current_price = new_price
        return new_price

    def generate_volume(self):
        """
        Generate volume based on price volatility
        Higher volatility = higher volume
        """
        base_volume = 10000
        volatility_factor = abs(np.random.normal(0, 1)) * self.volatility * 50000
        return int(base_volume + volatility_factor)

    def generate_bid_ask(self):
        """
        Generate bid/ask spread
        Returns dict with bid and ask prices
        """
        spread_percentage = 0.001 + (np.random.random() * 0.002)  # 0.1% to 0.3%
        spread = self.current_price * spread_percentage

        bid = round(self.current_price - spread / 2, 2)
        ask = round(self.current_price + spread / 2, 2)

        return {"bid": bid, "ask": ask}

    def generate_tick(self):
        """
        Generate a complete tick data point
        Returns dict with all tick data
        """
        price = self.generate_next_price()
        volume = self.generate_volume()
        bid_ask = self.generate_bid_ask()

        return {
            "ticker": self.ticker,
            "price": round(price, 2),
            "volume": volume,
            "bid": bid_ask["bid"],
            "ask": bid_ask["ask"],
            "timestamp": int(time.time() * 1000)
        }

    def reset(self, start_price=None):
        """Reset to initial state"""
        if start_price is not None:
            self.current_price = start_price
