"""
Live OHLC Chart Module

Provides real-time candlestick charting capabilities for the Synthetic Market Data API.

Quick Start:
    from src.chart.live_chart import LiveOHLCChart

    chart = LiveOHLCChart(
        ws_url="ws://localhost:3000/ws",
        tickers=["SYNTH"],
        bar_interval_seconds=5
    )
    chart.start()

See src/chart/README.md for full documentation.
"""

from .live_chart import LiveOHLCChart, OHLCBar

__all__ = ['LiveOHLCChart', 'OHLCBar']
__version__ = '1.0.0'
