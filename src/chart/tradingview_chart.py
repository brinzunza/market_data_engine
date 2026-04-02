"""
TradingView-style Live Chart using Plotly
Interactive candlestick chart with volume, indicators, and real-time updates
"""

import asyncio
import json
import websockets
from datetime import datetime
from collections import deque
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import webbrowser
import tempfile
import os


class OHLCBar:
    def __init__(self, timestamp):
        self.timestamp = timestamp
        self.open = None
        self.high = None
        self.low = None
        self.close = None
        self.volume = 0
        self.count = 0

    def update(self, price, volume):
        if self.open is None:
            self.open = price
        if self.high is None or price > self.high:
            self.high = price
        if self.low is None or price < self.low:
            self.low = price
        self.close = price
        self.volume += volume
        self.count += 1

    def is_complete(self):
        return all([self.open, self.high, self.low, self.close])


class TradingViewChart:
    def __init__(self, ws_url="ws://localhost:3000/ws", tickers=None,
                 bar_interval_seconds=5, max_bars=100):
        self.ws_url = ws_url
        self.tickers = tickers or ["SYNTH"]
        self.bar_interval = bar_interval_seconds
        self.max_bars = max_bars

        # Data storage per ticker
        self.bars_data = {ticker: deque(maxlen=max_bars) for ticker in self.tickers}
        self.current_bars = {ticker: None for ticker in self.tickers}
        self.tick_counts = {ticker: 0 for ticker in self.tickers}

        self.is_running = True

    def _get_bar_timestamp(self, tick_timestamp):
        """Round timestamp to bar interval"""
        ts_seconds = tick_timestamp // 1000
        return (ts_seconds // self.bar_interval) * self.bar_interval * 1000

    def process_tick(self, tick):
        """Process incoming tick and update bars"""
        ticker = tick.get("ticker")
        if ticker not in self.tickers:
            return

        price = tick.get("price")
        volume = tick.get("volume", 0)
        timestamp = tick.get("timestamp")

        if not all([price, timestamp]):
            return

        bar_timestamp = self._get_bar_timestamp(timestamp)

        # Create new bar if needed
        if self.current_bars[ticker] is None or self.current_bars[ticker].timestamp != bar_timestamp:
            if self.current_bars[ticker] and self.current_bars[ticker].is_complete():
                self.bars_data[ticker].append(self.current_bars[ticker])
            self.current_bars[ticker] = OHLCBar(bar_timestamp)

        # Update current bar
        self.current_bars[ticker].update(price, volume)
        self.tick_counts[ticker] += 1

    def create_figure(self, ticker):
        """Create TradingView-style Plotly figure"""
        bars = list(self.bars_data[ticker])
        if self.current_bars[ticker] and self.current_bars[ticker].open is not None:
            bars.append(self.current_bars[ticker])

        if not bars:
            return None

        # Convert to dataframe
        df = pd.DataFrame([
            {
                'time': datetime.fromtimestamp(bar.timestamp / 1000),
                'open': bar.open,
                'high': bar.high,
                'low': bar.low,
                'close': bar.close,
                'volume': bar.volume
            }
            for bar in bars if bar.is_complete()
        ])

        if df.empty:
            return None

        # Create subplots: candlestick + volume
        fig = make_subplots(
            rows=2, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.03,
            row_heights=[0.7, 0.3],
            subplot_titles=(f'{ticker} - Live Chart', 'Volume')
        )

        # Candlestick chart
        fig.add_trace(
            go.Candlestick(
                x=df['time'],
                open=df['open'],
                high=df['high'],
                low=df['low'],
                close=df['close'],
                name='Price',
                increasing_line_color='#26a69a',
                decreasing_line_color='#ef5350',
                increasing_fillcolor='#26a69a',
                decreasing_fillcolor='#ef5350'
            ),
            row=1, col=1
        )

        # Volume bars
        colors = ['#26a69a' if close >= open else '#ef5350'
                  for close, open in zip(df['close'], df['open'])]

        fig.add_trace(
            go.Bar(
                x=df['time'],
                y=df['volume'],
                name='Volume',
                marker_color=colors,
                opacity=0.7
            ),
            row=2, col=1
        )

        # Calculate stats
        current_price = df['close'].iloc[-1]
        first_price = df['open'].iloc[0]
        change = current_price - first_price
        change_pct = (change / first_price * 100) if first_price else 0
        high_24h = df['high'].max()
        low_24h = df['low'].min()
        volume_total = df['volume'].sum()

        # Update layout with TradingView style
        fig.update_layout(
            title={
                'text': f'{ticker} | ${current_price:.2f} <span style="color: {"green" if change >= 0 else "red"}">{change:+.2f} ({change_pct:+.2f}%)</span>',
                'x': 0.5,
                'xanchor': 'center',
                'font': {'size': 20, 'family': 'Arial, sans-serif'}
            },
            xaxis_rangeslider_visible=False,
            template='plotly_dark',
            hovermode='x unified',
            height=800,
            showlegend=False,
            paper_bgcolor='#131722',
            plot_bgcolor='#131722',
            font=dict(color='#d1d4dc'),
            margin=dict(l=50, r=50, t=100, b=50)
        )

        # Add annotations for stats
        annotations_text = (
            f'High: ${high_24h:.2f} | '
            f'Low: ${low_24h:.2f} | '
            f'Volume: {volume_total:,.0f} | '
            f'Bars: {len(df)} | '
            f'Ticks: {self.tick_counts[ticker]:,}'
        )

        fig.add_annotation(
            text=annotations_text,
            xref='paper', yref='paper',
            x=0.5, y=1.08,
            showarrow=False,
            font=dict(size=12, color='#787b86'),
            xanchor='center'
        )

        # Update axes
        fig.update_xaxes(
            gridcolor='#1e222d',
            showgrid=True,
            zeroline=False
        )

        fig.update_yaxes(
            gridcolor='#1e222d',
            showgrid=True,
            zeroline=False,
            side='right'
        )

        return fig

    async def websocket_listener(self):
        """Listen to WebSocket for real-time data"""
        try:
            async with websockets.connect(self.ws_url) as ws:
                print(f"✓ Connected to {self.ws_url}")

                # Wait for welcome
                await ws.recv()

                # Subscribe to tickers
                await ws.send(json.dumps({
                    "type": "subscribe",
                    "tickers": self.tickers
                }))
                print(f"✓ Subscribed to: {', '.join(self.tickers)}")

                # Wait for confirmation
                await ws.recv()
                print("✓ Receiving live data...\n")

                # Listen for ticks
                while self.is_running:
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=1.0)
                        data = json.loads(msg)

                        if data.get("type") == "tick":
                            tick = data.get("data")
                            self.process_tick(tick)

                    except asyncio.TimeoutError:
                        await ws.send(json.dumps({"type": "ping"}))
                    except Exception as e:
                        print(f"✗ Error processing message: {e}")

        except Exception as e:
            print(f"✗ WebSocket connection failed: {e}")
            self.is_running = False

    async def chart_updater(self, update_interval=1.0):
        """Update chart periodically"""
        html_file = tempfile.mktemp(suffix='.html')
        opened_browser = False

        while self.is_running:
            try:
                # Create figure for first ticker (or create dashboard for multiple)
                if len(self.tickers) == 1:
                    fig = self.create_figure(self.tickers[0])
                else:
                    fig = self.create_dashboard()

                if fig:
                    fig.write_html(html_file, auto_open=False)

                    if not opened_browser:
                        webbrowser.open(f'file://{html_file}')
                        opened_browser = True
                        print(f"✓ Chart opened in browser: {html_file}")
                        print("  Refresh browser to see updates (auto-refresh not available in file mode)")
                        print("  Press Ctrl+C to stop\n")

                await asyncio.sleep(update_interval)

            except Exception as e:
                print(f"✗ Error updating chart: {e}")
                await asyncio.sleep(update_interval)

    def create_dashboard(self):
        """Create multi-ticker dashboard"""
        rows = len(self.tickers)

        fig = make_subplots(
            rows=rows, cols=1,
            shared_xaxes=False,
            vertical_spacing=0.05,
            subplot_titles=self.tickers
        )

        for idx, ticker in enumerate(self.tickers, 1):
            bars = list(self.bars_data[ticker])
            if self.current_bars[ticker] and self.current_bars[ticker].open is not None:
                bars.append(self.current_bars[ticker])

            if not bars:
                continue

            df = pd.DataFrame([
                {
                    'time': datetime.fromtimestamp(bar.timestamp / 1000),
                    'open': bar.open,
                    'high': bar.high,
                    'low': bar.low,
                    'close': bar.close,
                }
                for bar in bars if bar.is_complete()
            ])

            if df.empty:
                continue

            fig.add_trace(
                go.Candlestick(
                    x=df['time'],
                    open=df['open'],
                    high=df['high'],
                    low=df['low'],
                    close=df['close'],
                    name=ticker,
                    increasing_line_color='#26a69a',
                    decreasing_line_color='#ef5350'
                ),
                row=idx, col=1
            )

        fig.update_layout(
            template='plotly_dark',
            height=400 * rows,
            showlegend=False,
            xaxis_rangeslider_visible=False,
            paper_bgcolor='#131722',
            plot_bgcolor='#131722'
        )

        fig.update_xaxes(gridcolor='#1e222d', showgrid=True)
        fig.update_yaxes(gridcolor='#1e222d', showgrid=True, side='right')

        return fig

    def start(self, chart_update_interval=2.0, display_mode="browser"):
        """Start the live chart"""
        print("=" * 70)
        print("TRADINGVIEW-STYLE LIVE CHART")
        print("=" * 70)
        print(f"WebSocket: {self.ws_url}")
        print(f"Tickers: {', '.join(self.tickers)}")
        print(f"Bar Interval: {self.bar_interval}s")
        print(f"Max Bars: {self.max_bars}")
        print(f"Chart Update: {chart_update_interval}s")
        print("=" * 70)
        print()

        async def run():
            tasks = [
                asyncio.create_task(self.websocket_listener()),
                asyncio.create_task(self.chart_updater(chart_update_interval))
            ]

            try:
                await asyncio.gather(*tasks)
            except KeyboardInterrupt:
                print("\n✓ Stopping chart...")
                self.is_running = False
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)

        asyncio.run(run())


def main():
    import argparse

    parser = argparse.ArgumentParser(description='TradingView-Style Live Chart')
    parser.add_argument('--ws-url', default='ws://localhost:3000/ws',
                       help='WebSocket URL')
    parser.add_argument('--tickers', default='SYNTH',
                       help='Comma-separated ticker symbols (e.g., SYNTH,TECH,FINANCE)')
    parser.add_argument('--interval', type=int, default=5,
                       help='OHLC bar interval in seconds')
    parser.add_argument('--max-bars', type=int, default=100,
                       help='Maximum bars to display')
    parser.add_argument('--update-rate', type=float, default=2.0,
                       help='Chart update rate in seconds')

    args = parser.parse_args()

    tickers = [t.strip().upper() for t in args.tickers.split(',')]

    chart = TradingViewChart(
        ws_url=args.ws_url,
        tickers=tickers,
        bar_interval_seconds=args.interval,
        max_bars=args.max_bars
    )

    chart.start(chart_update_interval=args.update_rate)


if __name__ == "__main__":
    main()
