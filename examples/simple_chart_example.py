"""
Simple example of using the Live OHLC Chart

This script demonstrates how to create a live candlestick chart
that displays real-time market data from the WebSocket API.
"""

import sys
import os

# Add src to path so we can import the chart module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.chart.live_chart import LiveOHLCChart


def example_single_ticker():
    """Example: Single ticker with default settings"""
    print("Example 1: Single Ticker (SYNTH)")
    print("-" * 50)

    chart = LiveOHLCChart(
        ws_url="ws://localhost:3000/ws",
        tickers=["SYNTH"],
        bar_interval_seconds=5,
        max_bars=100
    )

    chart.start(chart_update_interval=1.0, display_mode="browser")


def example_multiple_tickers():
    """Example: Multiple tickers dashboard"""
    print("Example 2: Multiple Tickers Dashboard")
    print("-" * 50)

    chart = LiveOHLCChart(
        ws_url="ws://localhost:3000/ws",
        tickers=["SYNTH", "TECH", "FINANCE"],
        bar_interval_seconds=5,
        max_bars=50
    )

    chart.start(chart_update_interval=1.0, display_mode="browser")


def example_day_trading():
    """Example: Day trading setup (fast 1-second bars)"""
    print("Example 3: Day Trading Setup")
    print("-" * 50)

    chart = LiveOHLCChart(
        ws_url="ws://localhost:3000/ws",
        tickers=["SYNTH"],
        bar_interval_seconds=1,  # 1-second bars
        max_bars=60  # Last 60 seconds
    )

    chart.start(chart_update_interval=0.5, display_mode="browser")


def example_save_to_file():
    """Example: Save chart to HTML file instead of opening browser"""
    print("Example 4: Save to HTML File")
    print("-" * 50)

    chart = LiveOHLCChart(
        ws_url="ws://localhost:3000/ws",
        tickers=["SYNTH", "TECH"],
        bar_interval_seconds=10,
        max_bars=100
    )

    # Run for a limited time then save
    import asyncio
    import signal

    async def run_for_duration(duration_seconds):
        """Run chart for specific duration then stop"""
        chart.is_running = True

        # Start tasks
        tasks = [
            asyncio.create_task(chart._websocket_listener()),
            asyncio.create_task(chart._chart_updater(1.0))
        ]

        print(f"Running for {duration_seconds} seconds...")

        # Wait for duration
        await asyncio.sleep(duration_seconds)

        # Stop
        print("Stopping...")
        chart.is_running = False

        # Cancel tasks
        for task in tasks:
            task.cancel()

        await asyncio.gather(*tasks, return_exceptions=True)

        # Save chart
        fig = chart.get_current_figure()
        if fig:
            filename = "market_chart.html"
            fig.write_html(filename)
            print(f"✓ Chart saved to {filename}")

    # Run
    asyncio.run(run_for_duration(30))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Live OHLC Chart Examples')
    parser.add_argument(
        'example',
        nargs='?',
        choices=['single', 'multiple', 'daytrading', 'save'],
        default='single',
        help='Which example to run (default: single)'
    )

    args = parser.parse_args()

    print("=" * 60)
    print("Live OHLC Chart Examples")
    print("=" * 60)
    print("\nMake sure the API is running:")
    print("  docker-compose up")
    print("\nPress Ctrl+C to stop the chart\n")
    print("=" * 60)
    print()

    if args.example == 'single':
        example_single_ticker()
    elif args.example == 'multiple':
        example_multiple_tickers()
    elif args.example == 'daytrading':
        example_day_trading()
    elif args.example == 'save':
        example_save_to_file()
