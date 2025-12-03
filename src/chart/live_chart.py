# -*- coding: utf-8 -*-
"""
Simple Live OHLC Candlestick Chart using matplotlib
Connects to WebSocket and displays real-time candlestick data
"""

import asyncio
import json
import websockets
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.patches import Rectangle
from datetime import datetime
from collections import defaultdict, deque
import threading
import queue


class OHLCBar:
    """Represents an OHLC bar"""
    def __init__(self, timestamp):
        self.timestamp = timestamp
        self.open = None
        self.high = None
        self.low = None
        self.close = None
        self.volume = 0

    def update(self, price, volume):
        if self.open is None:
            self.open = price
        if self.high is None or price > self.high:
            self.high = price
        if self.low is None or price < self.low:
            self.low = price
        self.close = price
        self.volume += volume

    def is_complete(self):
        return all([self.open, self.high, self.low, self.close])


class LiveChart:
    def __init__(self, ws_url="ws://localhost:3000/ws", ticker="SYNTH", bar_interval=5, max_bars=50):
        self.ws_url = ws_url
        self.ticker = ticker
        self.bar_interval = bar_interval  # seconds
        self.max_bars = max_bars

        # Data storage
        self.bars = deque(maxlen=max_bars)
        self.current_bar = None

        # Thread communication
        self.tick_queue = queue.Queue()
        self.is_running = True

        # Stats
        self.tick_count = 0

        # Setup plot
        self.fig, (self.ax1, self.ax2) = plt.subplots(2, 1, figsize=(12, 8),
                                                        gridspec_kw={'height_ratios': [3, 1]})
        self.fig.suptitle(f'{ticker} - Live OHLC Chart', fontsize=14, fontweight='bold')

    def _get_bar_timestamp(self, tick_timestamp):
        """Round timestamp to bar interval"""
        return (tick_timestamp // (self.bar_interval * 1000)) * (self.bar_interval * 1000)

    def process_tick(self, tick):
        """Process incoming tick and update bars"""
        price = tick.get("price")
        volume = tick.get("volume", 0)
        timestamp = tick.get("timestamp")

        if not all([price, timestamp]):
            return

        bar_timestamp = self._get_bar_timestamp(timestamp)

        # Create new bar if needed
        if self.current_bar is None or self.current_bar.timestamp != bar_timestamp:
            if self.current_bar and self.current_bar.is_complete():
                self.bars.append(self.current_bar)
            self.current_bar = OHLCBar(bar_timestamp)

        # Update current bar
        self.current_bar.update(price, volume)
        self.tick_count += 1

    def plot_candlestick(self, ax, bars):
        """Draw candlestick chart"""
        ax.clear()

        if not bars:
            ax.text(0.5, 0.5, 'Waiting for data...',
                   ha='center', va='center', transform=ax.transAxes)
            return

        for i, bar in enumerate(bars):
            if not bar.is_complete():
                continue

            # Determine color
            color = 'green' if bar.close >= bar.open else 'red'

            # Draw high-low line
            ax.plot([i, i], [bar.low, bar.high], color=color, linewidth=1)

            # Draw body rectangle
            body_height = abs(bar.close - bar.open)
            body_bottom = min(bar.open, bar.close)

            rect = Rectangle((i - 0.3, body_bottom), 0.6, body_height,
                           facecolor=color, edgecolor=color, alpha=0.8)
            ax.add_patch(rect)

        # Format
        ax.set_ylabel('Price ($)', fontweight='bold')
        ax.grid(True, alpha=0.3)
        ax.set_xlim(-1, len(bars))

        # Calculate price range
        if bars:
            all_highs = [b.high for b in bars if b.high]
            all_lows = [b.low for b in bars if b.low]
            if all_highs and all_lows:
                y_min, y_max = min(all_lows), max(all_highs)
                margin = (y_max - y_min) * 0.1
                ax.set_ylim(y_min - margin, y_max + margin)

        # Show current price
        if bars and bars[-1].close:
            current_price = bars[-1].close
            first_price = bars[0].open if bars[0].open else current_price
            change = current_price - first_price
            change_pct = (change / first_price * 100) if first_price else 0

            ax.set_title(f'Price: ${current_price:.2f} | '
                        f'Change: {change:+.2f} ({change_pct:+.2f}%)',
                        fontsize=10)

    def plot_volume(self, ax, bars):
        """Draw volume bars"""
        ax.clear()

        if not bars:
            return

        volumes = []
        colors = []

        for bar in bars:
            if bar.is_complete():
                volumes.append(bar.volume)
                colors.append('green' if bar.close >= bar.open else 'red')
            else:
                volumes.append(0)
                colors.append('gray')

        ax.bar(range(len(bars)), volumes, color=colors, alpha=0.6)
        ax.set_ylabel('Volume', fontweight='bold')
        ax.set_xlabel('Bars', fontweight='bold')
        ax.grid(True, alpha=0.3)
        ax.set_xlim(-1, len(bars))

    def update_plot(self, frame):
        """Animation update function"""
        # Process any new ticks from queue
        while not self.tick_queue.empty():
            try:
                tick = self.tick_queue.get_nowait()
                self.process_tick(tick)
            except queue.Empty:
                break

        # Get all bars including current
        all_bars = list(self.bars)
        if self.current_bar and self.current_bar.open is not None:
            all_bars.append(self.current_bar)

        # Update plots
        self.plot_candlestick(self.ax1, all_bars)
        self.plot_volume(self.ax2, all_bars)

        # Update stats in title
        self.fig.suptitle(
            f'{self.ticker} - Live OHLC Chart | '
            f'Ticks: {self.tick_count} | Bars: {len(self.bars)}',
            fontsize=14, fontweight='bold'
        )

    async def websocket_listener(self):
        """Listen to WebSocket in background thread"""
        try:
            async with websockets.connect(self.ws_url) as ws:
                print(f"[OK] Connected to {self.ws_url}")

                # Wait for connection message
                msg = await ws.recv()
                print(f"[OK] Connection confirmed")

                # Subscribe to ticker
                await ws.send(json.dumps({
                    "type": "subscribe",
                    "tickers": [self.ticker]
                }))
                print(f"[OK] Subscribed to {self.ticker}")

                # Wait for subscription confirmation
                msg = await ws.recv()
                print(f"[OK] Subscription confirmed")
                print(f"[OK] Receiving live data...\n")

                # Listen for ticks
                while self.is_running:
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=1.0)
                        data = json.loads(msg)

                        if data.get("type") == "tick":
                            tick = data.get("data")
                            if tick.get("ticker") == self.ticker:
                                self.tick_queue.put(tick)

                    except asyncio.TimeoutError:
                        # Send ping to keep connection alive
                        await ws.send(json.dumps({"type": "ping"}))
                    except Exception as e:
                        print(f"[ERROR] {e}")

        except Exception as e:
            print(f"[ERROR] WebSocket connection failed: {e}")
            self.is_running = False

    def start_websocket_thread(self):
        """Start WebSocket listener in background thread"""
        def run_async_loop():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.websocket_listener())

        thread = threading.Thread(target=run_async_loop, daemon=True)
        thread.start()

    def start(self, update_interval=500):
        """Start the live chart"""
        print("=" * 70)
        print("LIVE OHLC CANDLESTICK CHART")
        print("=" * 70)
        print(f"WebSocket: {self.ws_url}")
        print(f"Ticker: {self.ticker}")
        print(f"Bar Interval: {self.bar_interval}s")
        print(f"Update Rate: {update_interval}ms")
        print("=" * 70)
        print()

        # Start WebSocket listener in background
        self.start_websocket_thread()

        # Start animation
        ani = animation.FuncAnimation(
            self.fig,
            self.update_plot,
            interval=update_interval,
            cache_frame_data=False
        )

        try:
            plt.tight_layout()
            plt.show()
        except KeyboardInterrupt:
            print("\n[STOP] Chart stopped")
        finally:
            self.is_running = False


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Live OHLC Chart')
    parser.add_argument('--ws-url', default='ws://localhost:3000/ws',
                       help='WebSocket URL')
    parser.add_argument('--ticker', default='SYNTH',
                       help='Ticker symbol')
    parser.add_argument('--interval', type=int, default=5,
                       help='OHLC bar interval in seconds')
    parser.add_argument('--max-bars', type=int, default=50,
                       help='Maximum bars to display')
    parser.add_argument('--update-rate', type=int, default=500,
                       help='Chart update rate in milliseconds')

    args = parser.parse_args()

    chart = LiveChart(
        ws_url=args.ws_url,
        ticker=args.ticker,
        bar_interval=args.interval,
        max_bars=args.max_bars
    )

    chart.start(update_interval=args.update_rate)


if __name__ == "__main__":
    main()
