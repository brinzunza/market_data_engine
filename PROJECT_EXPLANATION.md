# Synthetic Market Data API - Complete Project Explanation

## Table of Contents
- [Overview](#overview)
- [What Problem Does This Solve?](#what-problem-does-this-solve)
- [Architecture Overview](#architecture-overview)
- [Core Components](#core-components)
- [Data Flow](#data-flow)
- [How Each Part Works](#how-each-part-works)
- [API Endpoints](#api-endpoints)
- [How to Use It](#how-to-use-it)

---

## Overview

This is a **real-time synthetic stock market data API** built with **Python** that generates realistic fake stock market data and makes it available through both REST API endpoints and WebSocket connections. Think of it as a simulator that creates stock prices that look and behave like real stocks, but are completely artificial.

### Why "Synthetic" Data?

Synthetic means "artificially created." Instead of using real stock market data (which requires expensive subscriptions and has legal restrictions), this project **generates its own realistic market data** using mathematical models. This is perfect for:
- Testing trading algorithms
- Building trading dashboards
- Learning how stock markets work
- Developing financial applications without paying for real data

---

## What Problem Does This Solve?

### The Problem:
If you want to build a stock trading app, you need stock market data. But real-time market data is:
1. **Expensive** - Real market data providers charge thousands of dollars per month
2. **Restricted** - Legal agreements limit how you can use the data
3. **Hard to test with** - You can't control what happens in real markets

### The Solution:
This project creates an infinite stream of realistic fake stock prices that:
- Behave like real stocks (go up and down realistically)
- Are free to use
- Can be customized (control volatility, price ranges, etc.)
- Update in real-time
- Are stored in a database for historical analysis

---

## Architecture Overview

The system is built using a **microservices architecture** with these main parts:

```
┌─────────────────────────────────────────────────────────────┐
│                    CLIENT APPLICATIONS                       │
│  (Web browsers, trading apps, data visualization tools)     │
└────────────────────┬───────────────────┬────────────────────┘
                     │                   │
          ┌──────────▼──────────┐   ┌───▼──────────────┐
          │   REST API          │   │   WebSocket      │
          │   (HTTP Requests)   │   │   (Live Stream)  │
          └──────────┬──────────┘   └───┬──────────────┘
                     │                   │
          ┌──────────▼───────────────────▼──────────────┐
          │       API SERVER (FastAPI/Python)           │
          │  - Handles HTTP requests                     │
          │  - Manages WebSocket connections             │
          │  - Reads from database                       │
          └──────────┬──────────────────┬────────────────┘
                     │                  │
          ┌──────────▼──────┐    ┌─────▼──────────────┐
          │   TimescaleDB    │    │   Kafka Message    │
          │   (Database)     │    │   Broker           │
          │                  │    │                    │
          │  Stores all      │    │  Distributes data  │
          │  tick data and   │    │  between services  │
          │  aggregated bars │    │                    │
          └──────────▲───────┘    └─────▲──────┬───────┘
                     │                  │      │
          ┌──────────┴──────┐    ┌─────┴──┐ ┌─▼────────┐
          │  Data Processor │    │  Data  │ │WebSocket │
          │                 │    │  Gen.  │ │Consumer  │
          │  - Consumes     │    │        │ │          │
          │    from Kafka   │    │Creates │ │Streams   │
          │  - Writes to DB │    │fake    │ │to clients│
          └─────────────────┘    │prices  │ └──────────┘
                                 └────────┘
```

---

## Core Components

### 1. **Data Generator** (`python_src/services/data_generator.py`)
**What it does:** Creates fake stock prices continuously

**How it works:**
- Runs a loop that generates new stock prices every 100 milliseconds
- Uses a mathematical model called **Geometric Brownian Motion (GBM)** to make prices realistic
- Creates data for 5 different stocks: SYNTH, TECH, FINANCE, ENERGY, HEALTH
- Publishes the generated data to **Kafka** (a message queue)

**Think of it as:** A machine that prints fake stock ticker tape 24/7

### 2. **Geometric Brownian Motion Model** (`python_src/models/gbm_generator.py`)
**What it does:** The mathematical brain that makes prices look realistic

**How it works:**
```
New Price = Current Price + Drift + Random Shock
```

- **Drift**: The general trend (stocks tend to go up over time)
- **Volatility**: How much the price jumps around
- **Random Shock**: Unpredictable price movements (like market chaos)

**Real-world example:**
- TECH stock has high volatility (30%) - jumps around a lot, like a tech startup
- FINANCE stock has low volatility (15%) - stable, like a bank stock

**Additional features:**
- Generates trading **volume** (how many shares are traded)
- Creates **bid/ask spread** (the difference between buying and selling price)
- Enforces price limits (stocks can't go below $10 or above their max)

### 3. **Kafka Message Broker** (Docker container)
**What it does:** Acts as a message highway between services

**How it works:**
- The Data Generator sends messages to Kafka
- Multiple consumers can read these messages simultaneously
- Messages are organized into "topics" (like channels)

**Think of it as:** A post office where:
- Generator drops off letters (market data)
- Processor and WebSocket consumer pick up copies of the letters
- Everyone gets the same information at the same time

**Why use Kafka?**
- **Decoupling**: Services don't need to talk directly to each other
- **Scalability**: Can handle millions of messages per second
- **Reliability**: If one service crashes, messages are saved for later

### 4. **Data Processor** (`python_src/services/data_processor.py`)
**What it does:** Saves the generated data to the database

**How it works:**
1. Listens to Kafka for new tick data
2. Buffers ticks in memory (collects 100 at a time)
3. Writes them to TimescaleDB in batches (more efficient)
4. Can aggregate ticks into OHLCV bars (Open, High, Low, Close, Volume)

**Batching explained:**
Instead of writing to database every time (slow):
```
Tick 1 → Write to DB
Tick 2 → Write to DB
Tick 3 → Write to DB (100 database calls = slow!)
```

It collects and writes in batches:
```
Tick 1 → Buffer
Tick 2 → Buffer
...
Tick 100 → Write all at once to DB (1 database call = fast!)
```

### 5. **TimescaleDB** (Docker container)
**What it does:** Specialized database for time-series data

**How it works:**
- Built on PostgreSQL (regular database)
- Optimized for data with timestamps
- Automatically partitions data by time (called "chunks")
- Has special features for time-series analysis

**Database Schema:**

**Table: `tickers`**
```
ticker  | name              | sector      | initial_price
--------|-------------------|-------------|---------------
SYNTH   | Synthetic Corp    | Technology  | 150.00
TECH    | Tech Innovations  | Technology  | 320.00
```

**Table: `market_ticks`** (hypertable - time-series optimized)
```
time                | ticker | price  | volume | bid    | ask
--------------------|--------|--------|--------|--------|-------
2025-10-02 14:30:01 | SYNTH  | 150.25 | 12000  | 150.20 | 150.30
2025-10-02 14:30:01 | TECH   | 321.50 | 13000  | 321.45 | 321.55
```

**Table: `market_bars`** (aggregated OHLCV data)
```
time                | ticker | timeframe | open   | high   | low    | close  | volume
--------------------|--------|-----------|--------|--------|--------|--------|--------
2025-10-02 14:30:00 | SYNTH  | 1m        | 150.00 | 150.50 | 149.80 | 150.25 | 120000
```

**Special Features:**
- **Hypertables**: Automatically partition data by time for fast queries
- **Continuous Aggregates**: Pre-calculated 1-minute bars (materialized views)
- **Retention Policy**: Automatically deletes data older than 30 days
- **Time-bucket queries**: Fast aggregation by time periods

### 6. **API Server** (`python_src/main.py`)
**What it does:** The main web server that handles all requests

**How it works:**
- Built with **FastAPI** (modern Python web framework)
- Listens on port 3000 by default
- Provides REST API endpoints
- Manages WebSocket connections
- Includes security features (rate limiting, CORS)

**Key Features:**
1. **FastAPI**: High-performance async framework
2. **CORS**: Allows requests from other domains
3. **Auto-generated docs**: Available at `/docs` (Swagger UI)
4. **Type validation**: Automatic request/response validation using Pydantic

### 7. **REST API Routes** (`python_src/routes/market_data.py`)
**What it does:** Defines all the API endpoints

**Available Endpoints:**

#### `GET /api/v1/tickers`
Lists all available stock tickers
```json
{
  "success": true,
  "data": [
    {
      "ticker": "SYNTH",
      "name": "Synthetic Corp",
      "sector": "Technology",
      "initial_price": "150.00"
    }
  ]
}
```

#### `GET /api/v1/quote/{ticker}`
Gets the latest price for a stock
```json
{
  "success": true,
  "data": {
    "time": "2025-10-02T14:30:01.000Z",
    "ticker": "SYNTH",
    "price": "150.25",
    "volume": 12000,
    "bid": "150.20",
    "ask": "150.30"
  }
}
```

#### `GET /api/v1/history/{ticker}`
Gets historical tick data with filters:
- `start`: Start time (default: 1 hour ago)
- `end`: End time (default: now)
- `limit`: Max records (default: 1000, max: 10000)

#### `GET /api/v1/bars/{ticker}`
Gets OHLCV candlestick bars:
- `timeframe`: 1m, 5m, 1h, 1d (default: 1m)
- `start`: Start time (default: 1 day ago)
- `end`: End time (default: now)
- `limit`: Max records (default: 500, max: 5000)

**How it works:**
1. First checks pre-aggregated `market_bars` table
2. If no data found, calculates on-the-fly using `time_bucket()`
3. Returns OHLCV data for charting

#### `GET /api/v1/stats/{ticker}`
Gets statistical analysis:
```json
{
  "success": true,
  "data": {
    "ticker": "SYNTH",
    "tick_count": 36000,
    "low": "148.50",
    "high": "152.30",
    "open": "150.00",
    "close": "150.25",
    "avg_price": "150.40",
    "total_volume": 432000000,
    "volatility": "1.25",
    "change": 0.25,
    "change_pct": 0.17,
    "period": "1d"
  }
}
```

### 8. **WebSocket Server** (`python_src/routes/websocket.py`)
**What it does:** Streams real-time data to connected clients

**How it works:**

1. **Client connects** to `ws://localhost:3000/ws`
2. **Server assigns** a unique ID and sends welcome message
3. **Client subscribes** to tickers they want to watch
4. **Server streams** tick data as it arrives from Kafka
5. **Client receives** real-time updates

**Message Protocol:**

**Client → Server:**
```json
// Subscribe to tickers
{
  "type": "subscribe",
  "tickers": ["SYNTH", "TECH"]
}

// Unsubscribe
{
  "type": "unsubscribe",
  "tickers": ["SYNTH"]
}

// Heartbeat
{
  "type": "ping"
}
```

**Server → Client:**
```json
// Connection established
{
  "type": "connected",
  "clientId": "abc-123-def",
  "timestamp": 1696258201000
}

// Real-time tick
{
  "type": "tick",
  "data": {
    "ticker": "SYNTH",
    "price": 150.25,
    "volume": 12000,
    "bid": 150.20,
    "ask": 150.30,
    "timestamp": 1696258201000
  }
}

// Heartbeat response
{
  "type": "pong",
  "timestamp": 1696258201000
}
```

**Key Features:**
- **Per-client subscriptions**: Each client only gets data they want
- **Tick caching**: New subscribers immediately get latest prices
- **Automatic cleanup**: Disconnected clients are removed
- **Error handling**: Invalid messages return error responses

---

## Data Flow

Here's how data moves through the entire system:

### Step-by-Step Flow:

```
1. DATA GENERATION
   ┌─────────────────────┐
   │  GBM Generator      │
   │  - Calculates price │──┐
   │  - Adds volume      │  │
   │  - Creates bid/ask  │  │
   └─────────────────────┘  │
                            │
   ┌─────────────────────┐  │
   │  Data Generator     │  │
   │  Every 100ms        │◄─┘
   └──────────┬──────────┘
              │ Publishes to Kafka
              ▼
   ┌─────────────────────┐
   │  Kafka Topic:       │
   │  "market-ticks"     │
   └──────────┬──────────┘
              │
         ┌────┴─────┐
         ▼          ▼
2. DATA STORAGE     3. LIVE STREAMING
   ┌─────────────┐    ┌──────────────┐
   │Data         │    │WebSocket     │
   │Processor    │    │Consumer      │
   └──────┬──────┘    └──────┬───────┘
          │                  │
          ▼                  ▼
   ┌─────────────┐    ┌──────────────┐
   │TimescaleDB  │    │Connected     │
   │- market_ticks│   │Clients       │
   │- market_bars │    │(Browsers,    │
   └──────┬──────┘    │ Apps)        │
          │           └──────────────┘
          ▼
4. API ACCESS
   ┌─────────────┐
   │REST API     │
   │Reads from DB│
   └──────┬──────┘
          ▼
   ┌─────────────┐
   │Clients      │
   │(HTTP)       │
   └─────────────┘
```

### Example: A Single Tick's Journey

1. **00:00.000** - GBM calculates SYNTH price: $150.25
2. **00:00.001** - Data Generator creates tick object
3. **00:00.002** - Tick published to Kafka topic "market-ticks"
4. **00:00.003** - Data Processor receives tick from Kafka
5. **00:00.004** - Tick added to buffer (waiting for 99 more)
6. **00:00.005** - WebSocket Consumer receives tick from Kafka
7. **00:00.006** - Tick cached in memory
8. **00:00.007** - Tick broadcast to all subscribed WebSocket clients
9. **00:01.000** - Buffer full (100 ticks), Data Processor writes to database
10. **Later** - REST API clients can query this historical data

---

## How Each Part Works

### The Mathematical Model (GBM)

**Geometric Brownian Motion Formula:**
```
ΔS = μ × S × Δt + σ × S × √Δt × Z

Where:
- S = Current stock price
- μ = Drift (expected return) - like stock's general direction
- σ = Volatility (standard deviation) - how wild the swings are
- Δt = Time step (0.0001 = very small increment)
- Z = Random number from normal distribution
```

**In plain English:**
```
Price Change = Expected Growth + Random Market Chaos

New Price = Old Price + Price Change
```

**Example for TECH stock:**
```
Current Price: $320.00
Drift: 8% annually (0.08)
Volatility: 30% annually (0.30)
Time step: 0.0001 (100ms = 0.0001 of a year)

Drift term = 0.08 × 320 × 0.0001 = $0.00256
Random shock = 0.30 × 320 × √0.0001 × (random: -0.5) = -$0.48
Price change = $0.00256 - $0.48 = -$0.477

New Price = $320.00 - $0.477 = $319.52
```

### The Database Optimization

**Why TimescaleDB?**

Regular PostgreSQL struggles with time-series data:
- Millions of rows make queries slow
- Indexes get huge
- Old data takes up space

TimescaleDB fixes this by:

1. **Hypertables**: Automatically partitions data into "chunks"
   ```
   market_ticks table
   ├── Chunk 1: Oct 1, 2025 data (fast to query)
   ├── Chunk 2: Oct 2, 2025 data (fast to query)
   └── Chunk 3: Oct 3, 2025 data (fast to query)

   Instead of scanning millions of rows, only scan relevant chunk!
   ```

2. **Continuous Aggregates**: Pre-calculated summaries
   ```sql
   -- This runs automatically every minute
   CREATE MATERIALIZED VIEW market_bars_1min AS
   SELECT
     time_bucket('1 minute', time) as time,
     ticker,
     FIRST(price, time) as open,    -- First price in the minute
     MAX(price) as high,             -- Highest price
     MIN(price) as low,              -- Lowest price
     LAST(price, time) as close,    -- Last price in the minute
     SUM(volume) as volume           -- Total volume
   FROM market_ticks
   GROUP BY time_bucket('1 minute', time), ticker;
   ```

   When you ask for 1-minute bars, database just reads pre-calculated view (instant) instead of calculating from raw ticks (slow).

3. **Retention Policies**: Auto-delete old data
   ```sql
   -- Automatically drops data older than 30 days
   SELECT add_retention_policy('market_ticks', INTERVAL '30 days');
   ```

### The Message Queue (Kafka)

**Why not just write directly to database?**

**Without Kafka:**
```
Generator → Database (what if DB is down? data lost!)
         → WebSocket (what if no clients connected? wasted effort!)
```

**With Kafka:**
```
Generator → Kafka (always available, data buffered)
            ├→ Processor → Database (reads at own pace)
            ├→ WebSocket (reads at own pace)
            └→ Future services (easy to add!)
```

**Kafka Benefits:**
- **Reliability**: Messages stored on disk, never lost
- **Buffering**: If database is slow, messages queue up
- **Replay**: Can re-process old messages
- **Scalability**: Can add more consumers easily

---

## API Endpoints

### Complete Endpoint Reference

#### 1. Health Check
```bash
GET /health

Response:
{
  "status": "healthy",
  "timestamp": "2025-10-02T14:30:01.000Z",
  "uptime": 3600.5
}
```

#### 2. API Information
```bash
GET /

Response:
{
  "name": "Synthetic Market Data API",
  "version": "1.0.0",
  "description": "Real-time synthetic stock market data...",
  "endpoints": {
    "rest": { ... },
    "websocket": { ... }
  }
}
```

#### 3. List Tickers
```bash
GET /api/v1/tickers

Response:
{
  "success": true,
  "data": [
    {
      "ticker": "SYNTH",
      "name": "Synthetic Corp",
      "sector": "Technology",
      "initial_price": "150.00",
      "created_at": "2025-10-02T14:00:00.000Z"
    },
    ...
  ]
}
```

#### 4. Latest Quote
```bash
GET /api/v1/quote/SYNTH

Response:
{
  "success": true,
  "data": {
    "time": "2025-10-02T14:30:01.123Z",
    "ticker": "SYNTH",
    "price": "150.25",
    "volume": 12000,
    "bid": "150.20",
    "ask": "150.30"
  }
}
```

#### 5. Historical Data
```bash
GET /api/v1/history/SYNTH?start=2025-10-02T14:00:00Z&end=2025-10-02T15:00:00Z&limit=1000

Response:
{
  "success": true,
  "data": [
    {
      "time": "2025-10-02T14:00:00.100Z",
      "ticker": "SYNTH",
      "price": "150.00",
      "volume": 11500,
      "bid": "149.95",
      "ask": "150.05"
    },
    ...
  ],
  "meta": {
    "ticker": "SYNTH",
    "start": "2025-10-02T14:00:00Z",
    "end": "2025-10-02T15:00:00Z",
    "count": 1000
  }
}
```

#### 6. OHLCV Bars
```bash
GET /api/v1/bars/SYNTH?timeframe=1m&start=2025-10-02T14:00:00Z&limit=60

Response:
{
  "success": true,
  "data": [
    {
      "time": "2025-10-02T14:00:00Z",
      "ticker": "SYNTH",
      "timeframe": "1m",
      "open": "150.00",
      "high": "150.50",
      "low": "149.80",
      "close": "150.25",
      "volume": "120000"
    },
    ...
  ],
  "meta": {
    "ticker": "SYNTH",
    "timeframe": "1m",
    "start": "2025-10-02T14:00:00Z",
    "end": "2025-10-02T15:00:00Z",
    "count": 60
  }
}
```

#### 7. Statistics
```bash
GET /api/v1/stats/SYNTH?period=1d

Response:
{
  "success": true,
  "data": {
    "ticker": "SYNTH",
    "tick_count": "36000",
    "low": "148.50",
    "high": "152.30",
    "open": "150.00",
    "close": "150.25",
    "avg_price": "150.40",
    "total_volume": "432000000",
    "volatility": "1.25",
    "change": 0.25,
    "change_pct": 0.17,
    "period": "1d"
  }
}
```

### WebSocket Protocol

#### Connection
```python
import websockets
import json

async with websockets.connect('ws://localhost:3000/ws') as websocket:
    # Server sends welcome
    welcome = await websocket.recv()
    # {
    #   "type": "connected",
    #   "clientId": "550e8400-e29b-41d4-a716-446655440000",
    #   "timestamp": 1696258201000
    # }
```

#### Subscribe to Tickers
```python
# Send subscription request
await websocket.send(json.dumps({
    'type': 'subscribe',
    'tickers': ['SYNTH', 'TECH']
}))

# Receive confirmation
confirmation = await websocket.recv()
# {
#   "type": "subscribed",
#   "tickers": ["SYNTH", "TECH"],
#   "timestamp": 1696258201000
# }

# Receive real-time ticks
while True:
    tick = await websocket.recv()
    # {
    #   "type": "tick",
    #   "data": {
    #     "ticker": "SYNTH",
    #     "price": 150.25,
    #     "volume": 12000,
    #     "bid": 150.20,
    #     "ask": 150.30,
    #     "timestamp": 1696258201000
    #   }
    # }
```

#### Unsubscribe
```python
await websocket.send(json.dumps({
    'type': 'unsubscribe',
    'tickers': ['SYNTH']
}))
```

#### Heartbeat
```python
# Send ping
await websocket.send(json.dumps({'type': 'ping'}))

# Receive pong
pong = await websocket.recv()
# {
#   "type": "pong",
#   "timestamp": 1696258201000
# }
```

---

## How to Use It

### Initial Setup

1. **Start Infrastructure (Docker)**
   ```bash
   docker-compose up -d
   ```
   This starts:
   - TimescaleDB (database) on port 5432
   - Zookeeper (Kafka dependency) on port 2181
   - Kafka (message broker) on port 9092

2. **Initialize Database**
   ```bash
   python -m python_src.db.init
   ```
   This creates:
   - Tables (tickers, market_ticks, market_bars)
   - Hypertables (time-series optimization)
   - Continuous aggregates (pre-calculated 1min bars)
   - Sample ticker data

3. **Start Data Generator**
   ```bash
   python -m python_src.services.data_generator
   ```
   Starts generating tick data every 100ms

4. **Start Data Processor** (optional, in another terminal)
   ```bash
   python -m python_src.services.data_processor
   ```
   Starts saving data to database

5. **Start API Server**
   ```bash
   python -m python_src.main
   # or
   uvicorn python_src.main:app --reload --port 3000
   ```
   API available at http://localhost:3000
   Swagger docs at http://localhost:3000/docs

### Testing the API

#### Using cURL
```bash
# Get all tickers
curl http://localhost:3000/api/v1/tickers

# Get latest quote
curl http://localhost:3000/api/v1/quote/SYNTH

# Get 1-minute bars
curl "http://localhost:3000/api/v1/bars/SYNTH?timeframe=1m&limit=10"

# Get statistics
curl "http://localhost:3000/api/v1/stats/SYNTH?period=1h"
```

#### Using Python (REST API)
```python
import requests

# Fetch tickers
response = requests.get('http://localhost:3000/api/v1/tickers')
data = response.json()
print(data)

# Get latest quote
quote = requests.get('http://localhost:3000/api/v1/quote/SYNTH')
quote_data = quote.json()
print(quote_data['data'])

# Get historical bars for charting
bars = requests.get(
    'http://localhost:3000/api/v1/bars/SYNTH?timeframe=5m&limit=100'
)
bar_data = bars.json()
# Use bar_data['data'] to create a candlestick chart
```

#### Using Python (WebSocket)
```python
import asyncio
import websockets
import json

async def connect():
    async with websockets.connect('ws://localhost:3000/ws') as websocket:
        print('Connected to market data feed')

        # Subscribe to tickers
        await websocket.send(json.dumps({
            'type': 'subscribe',
            'tickers': ['SYNTH', 'TECH', 'FINANCE']
        }))

        # Listen for messages
        while True:
            message = json.loads(await websocket.recv())

            if message['type'] == 'tick':
                ticker = message['data']['ticker']
                price = message['data']['price']
                volume = message['data']['volume']
                print(f"{ticker}: ${price} (Volume: {volume})")

asyncio.run(connect())
```

### Stopping Everything

```bash
# Stop Python services (Ctrl+C in each terminal)
^C

# Stop Docker containers
docker-compose down

# Stop and remove all data
docker-compose down -v
```

---

## Configuration

### Environment Variables (`.env`)

```bash
# Server
PORT=3000                    # API server port
ENVIRONMENT=development      # development or production
API_VERSION=v1              # API version prefix

# Database
DB_HOST=localhost           # TimescaleDB host
DB_PORT=5432               # TimescaleDB port
DB_NAME=synthetic_market   # Database name
DB_USER=postgres           # Database user
DB_PASSWORD=postgres       # Database password

# Kafka
KAFKA_BROKERS=localhost:9092          # Kafka broker addresses
KAFKA_CLIENT_ID=synthetic-market-api  # Kafka client identifier
KAFKA_TOPIC_TICKS=market-ticks       # Topic for tick data
KAFKA_TOPIC_BARS=market-bars         # Topic for bar data

# Data Generation
GENERATOR_INTERVAL_MS=100             # Generate ticks every 100ms
TICKERS=SYNTH,TECH,FINANCE,ENERGY,HEALTH  # Active tickers
```

### Stock Configuration (in code)

Edit `python_src/services/data_generator.py` to customize stocks:

```python
TICKER_CONFIGS = {
    'CUSTOM': {
        'ticker': 'CUSTOM',
        'start_price': 100.0,    # Initial price
        'drift': 0.10,           # 10% annual growth
        'volatility': 0.25,      # 25% volatility
        'min_price': 10,         # Floor price
        'max_price': 1000        # Ceiling price
    }
}
```

---

## Use Cases

### 1. **Testing Trading Algorithms**
Use the API to test buy/sell strategies without risking real money:
```python
import requests

# Backtest a simple moving average strategy
bars = requests.get('http://localhost:3000/api/v1/bars/SYNTH?timeframe=1h&limit=100')
data = bars.json()

# Calculate 20-period moving average
prices = [float(bar['close']) for bar in data['data']]
sma20 = calculate_sma(prices, 20)

# Generate trading signals
if prices[-1] > sma20[-1]:
    print('BUY signal')
else:
    print('SELL signal')
```

### 2. **Building Trading Dashboards**
Create real-time stock monitoring interfaces using FastAPI and WebSockets

### 3. **Learning Market Mechanics**
Understand how markets work by observing:
- Price volatility patterns
- Volume correlations
- Bid-ask spreads
- Market statistics

### 4. **Performance Testing**
Test your application's ability to handle:
- High-frequency data updates
- Large historical data queries
- Multiple concurrent WebSocket connections

---

## Technical Concepts Explained

### What is a Hypertable?
Think of a regular table as a single filing cabinet. As you add more files, it gets harder to find things. A hypertable is like having multiple filing cabinets organized by date. When you need October 2025 data, you only open the October cabinet instead of searching through everything.

### What is a Continuous Aggregate?
Instead of calculating "what was the average price this hour" every time someone asks, the database calculates it once per hour and saves the answer. When someone asks later, it just reads the saved answer (instant) instead of recalculating (slow).

### What is Geometric Brownian Motion?
It's a mathematical formula that makes random numbers look like stock prices. Real stocks have:
1. A general trend (usually up over time) = drift
2. Random day-to-day fluctuations = volatility
3. Unpredictable events = random shocks

GBM combines these three to create realistic price movements.

### What is OHLCV?
**O**pen, **H**igh, **L**ow, **C**lose, **V**olume
- **Open**: First price in the time period
- **High**: Highest price reached
- **Low**: Lowest price reached
- **Close**: Last price in the time period
- **Volume**: Total shares traded

This is the data used to create candlestick charts.

### What is a Message Broker (Kafka)?
A message broker is like a post office for software. Instead of services talking directly to each other (which is fragile), they send messages through the broker. The broker ensures messages are delivered reliably, can be read multiple times, and are stored safely.

---

## Summary

This project creates a complete synthetic stock market data system using **Python**:

1. **Generates** realistic stock prices using mathematical models (NumPy)
2. **Distributes** data efficiently using Kafka message queues
3. **Stores** data in an optimized time-series database (TimescaleDB)
4. **Serves** data via REST API for historical analysis (FastAPI)
5. **Streams** data via WebSocket for real-time updates (FastAPI WebSockets)

**It's like having your own mini stock exchange that:**
- Runs 24/7
- Costs nothing
- Can be customized
- Never has legal restrictions
- Perfect for learning and testing

The architecture is production-ready and can be scaled to handle millions of data points per second if needed. Built with modern Python async/await patterns for high performance.
