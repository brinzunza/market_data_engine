"""
Live TradingView-style chart route
Self-contained HTML page with WebSocket-powered auto-updates
"""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

LIVE_CHART_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Live Chart - TradingView Style</title>
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }

body {
  background: #131722;
  color: #d1d4dc;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  min-height: 100vh;
  padding: 20px;
}

.container {
  max-width: 1600px;
  margin: 0 auto;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding: 15px 20px;
  background: #1e222d;
  border-radius: 8px;
}

.header h1 {
  font-size: 24px;
  font-weight: 600;
  color: #fff;
}

.controls {
  display: flex;
  gap: 10px;
  align-items: center;
}

.ticker-select, .interval-select {
  background: #131722;
  border: 1px solid #2a2e39;
  color: #d1d4dc;
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
}

.ticker-select:hover, .interval-select:hover {
  border-color: #434651;
}

.status {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  background: #131722;
  border-radius: 6px;
  font-size: 13px;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #787b86;
  transition: background 0.3s;
}

.status-dot.live {
  background: #26a69a;
  box-shadow: 0 0 8px #26a69a;
}

.stats-bar {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 10px;
  margin-bottom: 20px;
}

.stat-card {
  background: #1e222d;
  padding: 12px 16px;
  border-radius: 6px;
}

.stat-label {
  font-size: 11px;
  color: #787b86;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 4px;
}

.stat-value {
  font-size: 18px;
  font-weight: 600;
  color: #fff;
}

.stat-value.positive { color: #26a69a; }
.stat-value.negative { color: #ef5350; }

#chart {
  background: #1e222d;
  border-radius: 8px;
  padding: 20px;
  min-height: 600px;
}

.info-text {
  text-align: center;
  color: #787b86;
  padding: 40px;
  font-size: 14px;
}
</style>
</head>
<body>

<div class="container">
  <div class="header">
    <h1>📈 Live Chart</h1>
    <div class="controls">
      <select class="ticker-select" id="tickerSelect">
        <option value="SYNTH">SYNTH</option>
        <option value="TECH">TECH</option>
        <option value="FINANCE">FINANCE</option>
        <option value="ENERGY">ENERGY</option>
        <option value="HEALTH">HEALTH</option>
      </select>
      <select class="interval-select" id="intervalSelect">
        <option value="1">1s bars</option>
        <option value="5" selected>5s bars</option>
        <option value="10">10s bars</option>
        <option value="30">30s bars</option>
        <option value="60">1m bars</option>
      </select>
      <div class="status">
        <span class="status-dot" id="statusDot"></span>
        <span id="statusText">Connecting...</span>
      </div>
    </div>
  </div>

  <div class="stats-bar" id="statsBar">
    <div class="stat-card">
      <div class="stat-label">Price</div>
      <div class="stat-value" id="statPrice">—</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Change</div>
      <div class="stat-value" id="statChange">—</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">High</div>
      <div class="stat-value" id="statHigh">—</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Low</div>
      <div class="stat-value" id="statLow">—</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Volume</div>
      <div class="stat-value" id="statVolume">—</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Bars</div>
      <div class="stat-value" id="statBars">0</div>
    </div>
  </div>

  <div id="chart">
    <div class="info-text">Connecting to WebSocket...</div>
  </div>
</div>

<script>
(function(){
"use strict";

// Configuration
const WS_URL = (location.protocol==="https:"?"wss:":"ws:")+"//"+location.host+"/ws";
let currentTicker = "SYNTH";
let barInterval = 5; // seconds
const MAX_BARS = 100;

// Data storage
class OHLCBar {
  constructor(timestamp) {
    this.timestamp = timestamp;
    this.open = null;
    this.high = null;
    this.low = null;
    this.close = null;
    this.volume = 0;
  }

  update(price, volume) {
    if (this.open === null) this.open = price;
    if (this.high === null || price > this.high) this.high = price;
    if (this.low === null || price < this.low) this.low = price;
    this.close = price;
    this.volume += volume;
  }

  isComplete() {
    return this.open !== null && this.high !== null &&
           this.low !== null && this.close !== null;
  }
}

let bars = [];
let currentBar = null;
let ws = null;
let reconnectDelay = 1000;
let tickCount = 0;
let isLoadingHistory = false;

// Get bar timestamp
function getBarTimestamp(tickTimestamp) {
  const tsSeconds = Math.floor(tickTimestamp / 1000);
  return Math.floor(tsSeconds / barInterval) * barInterval * 1000;
}

// Load historical bars from API
async function loadHistoricalBars(ticker, intervalSeconds, maxBars = 100) {
  if (isLoadingHistory) return;
  isLoadingHistory = true;

  try {
    console.log(`Loading historical bars for ${ticker}...`);

    // Calculate time range based on interval
    const now = Date.now();
    const startTime = now - (intervalSeconds * maxBars * 2 * 1000); // 2x to ensure enough data
    const endTime = now;

    // Fetch historical ticks
    const response = await fetch(
      `/api/v1/history/${ticker}?` +
      `start=${new Date(startTime).toISOString()}&` +
      `end=${new Date(endTime).toISOString()}&` +
      `limit=10000`
    );

    if (!response.ok) {
      console.error('Failed to load historical data:', response.statusText);
      return;
    }

    const data = await response.json();
    const ticks = data.data || [];

    if (ticks.length === 0) {
      console.log('No historical data available');
      return;
    }

    console.log(`Loaded ${ticks.length} historical ticks`);

    // Group ticks into bars
    const barMap = new Map();

    ticks.forEach(tick => {
      const barTimestamp = getBarTimestamp(tick.timestamp);

      if (!barMap.has(barTimestamp)) {
        barMap.set(barTimestamp, new OHLCBar(barTimestamp));
      }

      barMap.get(barTimestamp).update(tick.price, tick.volume);
    });

    // Convert to array and sort by timestamp
    const historicalBars = Array.from(barMap.values())
      .filter(bar => bar.isComplete())
      .sort((a, b) => a.timestamp - b.timestamp)
      .slice(-maxBars); // Keep only last maxBars

    bars = historicalBars;
    console.log(`Created ${bars.length} historical bars`);

    // Update chart with historical data
    updateChart();

  } catch (error) {
    console.error('Error loading historical bars:', error);
  } finally {
    isLoadingHistory = false;
  }
}

// Process tick
function processTick(tick) {
  if (tick.ticker !== currentTicker) return;

  const price = tick.price;
  const volume = tick.volume || 0;
  const timestamp = tick.timestamp;

  if (!price || !timestamp) return;

  const barTimestamp = getBarTimestamp(timestamp);

  // Create new bar if needed
  if (!currentBar || currentBar.timestamp !== barTimestamp) {
    if (currentBar && currentBar.isComplete()) {
      bars.push(currentBar);
      if (bars.length > MAX_BARS) bars.shift();
    }
    currentBar = new OHLCBar(barTimestamp);
  }

  currentBar.update(price, volume);
  tickCount++;

  // Update chart
  updateChart();
}

// Create/update chart
function updateChart() {
  const allBars = [...bars];
  if (currentBar && currentBar.open !== null) {
    allBars.push(currentBar);
  }

  if (allBars.length === 0) return;

  // Prepare data
  const times = [];
  const opens = [];
  const highs = [];
  const lows = [];
  const closes = [];
  const volumes = [];

  allBars.forEach(bar => {
    if (!bar.isComplete()) return;
    times.push(new Date(bar.timestamp));
    opens.push(bar.open);
    highs.push(bar.high);
    lows.push(bar.low);
    closes.push(bar.close);
    volumes.push(bar.volume);
  });

  if (times.length === 0) return;

  // Volume colors
  const volumeColors = closes.map((close, i) =>
    close >= opens[i] ? '#26a69a' : '#ef5350'
  );

  // Create traces
  const candlestick = {
    type: 'candlestick',
    x: times,
    open: opens,
    high: highs,
    low: lows,
    close: closes,
    increasing: {line: {color: '#26a69a'}, fillcolor: '#26a69a'},
    decreasing: {line: {color: '#ef5350'}, fillcolor: '#ef5350'},
    name: currentTicker,
    xaxis: 'x',
    yaxis: 'y'
  };

  const volumeBar = {
    type: 'bar',
    x: times,
    y: volumes,
    marker: {color: volumeColors},
    opacity: 0.7,
    name: 'Volume',
    xaxis: 'x',
    yaxis: 'y2'
  };

  // Layout
  const layout = {
    paper_bgcolor: '#1e222d',
    plot_bgcolor: '#1e222d',
    font: {color: '#d1d4dc', family: 'Arial'},
    showlegend: false,
    xaxis: {
      rangeslider: {visible: false},
      gridcolor: '#2a2e39',
      showgrid: true,
      zeroline: false
    },
    yaxis: {
      domain: [0.3, 1],
      gridcolor: '#2a2e39',
      showgrid: true,
      zeroline: false,
      side: 'right'
    },
    yaxis2: {
      domain: [0, 0.25],
      gridcolor: '#2a2e39',
      showgrid: true,
      zeroline: false,
      side: 'right'
    },
    margin: {l: 50, r: 50, t: 30, b: 50},
    hovermode: 'x unified'
  };

  const config = {
    responsive: true,
    displayModeBar: true,
    displaylogo: false
  };

  Plotly.react('chart', [candlestick, volumeBar], layout, config);

  // Update stats
  updateStats(allBars);
}

// Update statistics
function updateStats(allBars) {
  if (allBars.length === 0) return;

  const completeBars = allBars.filter(b => b.isComplete());
  if (completeBars.length === 0) return;

  const currentPrice = completeBars[completeBars.length - 1].close;
  const firstPrice = completeBars[0].open;
  const change = currentPrice - firstPrice;
  const changePct = (change / firstPrice * 100);

  const high = Math.max(...completeBars.map(b => b.high));
  const low = Math.min(...completeBars.map(b => b.low));
  const totalVolume = completeBars.reduce((sum, b) => sum + b.volume, 0);

  document.getElementById('statPrice').textContent = `$${currentPrice.toFixed(2)}`;

  const changeEl = document.getElementById('statChange');
  changeEl.textContent = `${change >= 0 ? '+' : ''}${change.toFixed(2)} (${changePct >= 0 ? '+' : ''}${changePct.toFixed(2)}%)`;
  changeEl.className = 'stat-value ' + (change >= 0 ? 'positive' : 'negative');

  document.getElementById('statHigh').textContent = `$${high.toFixed(2)}`;
  document.getElementById('statLow').textContent = `$${low.toFixed(2)}`;
  document.getElementById('statVolume').textContent = totalVolume.toLocaleString();
  document.getElementById('statBars').textContent = completeBars.length;
}

// WebSocket connection
function connect() {
  setStatus(false, 'Connecting...');

  ws = new WebSocket(WS_URL);

  ws.onopen = async () => {
    console.log('✓ WebSocket connected');
    reconnectDelay = 1000;
    setStatus(true, 'Live');

    // Load historical bars first
    await loadHistoricalBars(currentTicker, barInterval, MAX_BARS);

    // Subscribe to ticker for live updates
    ws.send(JSON.stringify({
      type: 'subscribe',
      tickers: [currentTicker]
    }));
  };

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);

      if (msg.type === 'tick') {
        processTick(msg.data);
      }
    } catch (e) {
      console.error('Error parsing message:', e);
    }
  };

  ws.onclose = () => {
    console.log('✗ WebSocket disconnected');
    setStatus(false, 'Reconnecting...');
    setTimeout(connect, reconnectDelay);
    reconnectDelay = Math.min(reconnectDelay * 2, 8000);
  };

  ws.onerror = (err) => {
    console.error('WebSocket error:', err);
  };
}

function setStatus(isLive, text) {
  const dot = document.getElementById('statusDot');
  const txt = document.getElementById('statusText');

  if (isLive) {
    dot.classList.add('live');
  } else {
    dot.classList.remove('live');
  }

  txt.textContent = text;
}

// Ticker change handler
document.getElementById('tickerSelect').addEventListener('change', (e) => {
  const newTicker = e.target.value;

  if (newTicker === currentTicker) return;

  console.log('Switching from', currentTicker, 'to', newTicker);

  // Unsubscribe from old ticker
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({
      type: 'unsubscribe',
      tickers: [currentTicker]
    }));
  }

  // Reset data
  currentTicker = newTicker;
  bars = [];
  currentBar = null;
  tickCount = 0;

  // Clear stats
  document.getElementById('statPrice').textContent = '—';
  document.getElementById('statChange').textContent = '—';
  document.getElementById('statChange').className = 'stat-value';
  document.getElementById('statHigh').textContent = '—';
  document.getElementById('statLow').textContent = '—';
  document.getElementById('statVolume').textContent = '—';
  document.getElementById('statBars').textContent = '0';

  // Clear existing chart by purging it
  Plotly.purge('chart');

  // Load historical bars and subscribe to new ticker
  (async () => {
    await loadHistoricalBars(currentTicker, barInterval, MAX_BARS);

    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: 'subscribe',
        tickers: [currentTicker]
      }));
      console.log('Subscribed to', currentTicker);
    }
  })();
});

// Interval change handler
document.getElementById('intervalSelect').addEventListener('change', (e) => {
  barInterval = parseInt(e.target.value);

  console.log('Bar interval changed to', barInterval, 'seconds');

  // Reset data
  bars = [];
  currentBar = null;
  tickCount = 0;

  // Clear stats
  document.getElementById('statPrice').textContent = '—';
  document.getElementById('statChange').textContent = '—';
  document.getElementById('statChange').className = 'stat-value';
  document.getElementById('statHigh').textContent = '—';
  document.getElementById('statLow').textContent = '—';
  document.getElementById('statVolume').textContent = '—';
  document.getElementById('statBars').textContent = '0';

  // Clear chart
  Plotly.purge('chart');

  // Reload historical bars with new interval
  loadHistoricalBars(currentTicker, barInterval, MAX_BARS);
});

// Start
connect();

})();
</script>
</body>
</html>
"""


@router.get("/chart", response_class=HTMLResponse)
async def live_chart():
    """Serve the live TradingView-style chart"""
    return HTMLResponse(content=LIVE_CHART_HTML)
