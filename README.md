<div style="margin-bottom: 20px;">
  <img src="phanes.jpg" alt="phanes" width="100%" style="display: block;"/>
</div>

# Synthetic Market Data API

A real-time synthetic stock market data generator and API.


## Features

- **Synthetic Data Generation**: Uses Geometric Brownian Motion (GBM) with NumPy for realistic stock price movements
- **Real-time Streaming**: WebSocket API for live market data feeds
- **Historical Data**: REST API with time-series optimized queries
- **Multiple Tickers**: Pre-configured with 5 synthetic stocks (SYNTH, TECH, FINANCE, ENERGY, HEALTH)
- **OHLCV Bars**: Aggregated candlestick data for multiple timeframes (1m, 5m, 1h, 1d)
- **TimescaleDB**: Optimized time-series database with automatic data retention
- **Production Ready**: Docker Compose for easy deployment, async I/O, and structured logging
- **Rate Limiting**: Includes proper rate limiting to prevent request floods
- **API Key Authentication**: Secure endpoints with API key authentication 

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Python 3.11+ (for local development)

### Easy Setup (Recommended)

1. Clone the repository:
```bash
git clone <your-repo-url>
cd synthDataAPI
```

2. Start everything with one command:
```bash
./start.sh
```

That's it! The script will:
- ✅ Build all Docker images
- 🚀 Start all services (PostgreSQL, Kafka, API, Generator, Processor)
- 🗄️ Initialize the database automatically
- 📊 Display all endpoints and useful information

3. Stop everything when done:
```bash
./stop.sh
```

### What Gets Started

The `start.sh` script launches:
- **PostgreSQL Database** (port 5432) - Time-series data storage
- **Kafka + Zookeeper** (port 9092) - Message streaming
- **Data Generator** - Creates synthetic market data using GBM
- **Data Processor** - Consumes Kafka and stores to database
- **API Server** (port 3000) - REST API + WebSocket endpoints

### Manual Setup (Alternative)

If you prefer manual control:

1. Copy environment variables:
```bash
cp .env.example .env
```

2. Start services:
```bash
docker-compose up -d
```

3. Initialize database:
```bash
docker-compose exec -T postgres psql -U postgres -d synthetic_market < python_src/db/schema.sql
```

## Authentication

All API endpoints (except `/`, `/health`, and `/docs`) require an API key for authentication.

**Include the API key in your request headers:**
```bash
X-API-Key: brunosapikey
```

**Example:**
```bash
# Get all tickers
http://localhost:3000/api/v1/tickers?api_key=brunosapikey

# Get SYNTH quote
http://localhost:3000/api/v1/quote/SYNTH?api_key=brunosapikey

# Get 1-minute bars
http://localhost:3000/api/v1/bars/SYNTH?api_key=brunosapikey&timeframe=1m&limit=10

# Get stats
http://localhost:3000/api/v1/stats/SYNTH?api_key=brunosapikey&period=1d
```

## API Endpoints

### REST API

Base URL: `http://localhost:3000/api/v1`

**Note:** All endpoints below require the `X-API-Key` header.

#### Get All Tickers
```bash
curl -H "X-API-Key: brunosapikey" http://localhost:3000/api/v1/tickers
```

**Response:**
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

#### Get Latest Quote
```bash
curl -H "X-API-Key: brunosapikey" http://localhost:3000/api/v1/quote/SYNTH
```

**Response:**
```json
{
  "success": true,
  "data": {
    "time": "2024-01-15T10:30:45.123Z",
    "ticker": "SYNTH",
    "price": "152.34",
    "volume": 12500,
    "bid": "152.28",
    "ask": "152.40"
  }
}
```

#### Get Historical Ticks
```
GET /history/:ticker?start=<ISO_DATE>&end=<ISO_DATE>&limit=<NUMBER>
```

**Parameters:**
- `start`: ISO timestamp (default: 1 hour ago)
- `end`: ISO timestamp (default: now)
- `limit`: max records (default: 1000, max: 10000)

#### Get OHLCV Bars
```
GET /bars/:ticker?timeframe=<1m|5m|1h|1d>&start=<ISO_DATE>&end=<ISO_DATE>&limit=<NUMBER>
```

**Parameters:**
- `timeframe`: `1m`, `5m`, `1h`, or `1d` (default: `1m`)
- `start`: ISO timestamp (default: 1 day ago)
- `end`: ISO timestamp (default: now)
- `limit`: max records (default: 500, max: 5000)

#### Get Statistics
```
GET /stats/:ticker?period=<1h|1d|7d|30d>
```

**Example:** `GET /stats/SYNTH?period=1d`

### WebSocket API

URL: `ws://localhost:3000/ws`

#### Connection

```python
import asyncio
import websockets
import json

async def connect():
    async with websockets.connect('ws://localhost:3000/ws') as websocket:
        # Receive welcome message
        message = await websocket.recv()
        print(f"Connected: {message}")

        # Subscribe to tickers
        await websocket.send(json.dumps({
            "type": "subscribe",
            "tickers": ["SYNTH", "TECH"]
        }))

        # Receive real-time ticks
        async for message in websocket:
            data = json.loads(message)
            print(f"Received: {data}")

asyncio.run(connect())
```

#### Subscribe to Tickers

```python
await websocket.send(json.dumps({
    "type": "subscribe",
    "tickers": ["SYNTH", "TECH"]
}))
```

#### Receive Real-time Ticks

```json
{
  "type": "tick",
  "data": {
    "ticker": "SYNTH",
    "price": 152.34,
    "volume": 12500,
    "bid": 152.28,
    "ask": 152.40,
    "timestamp": 1705318245123
  }
}
```

#### Unsubscribe

```python
await websocket.send(json.dumps({
    "type": "unsubscribe",
    "tickers": ["SYNTH"]
}))
```
## Ticker Configuration

The system includes 5 pre-configured synthetic tickers with different characteristics:

| Ticker | Name | Sector | Start Price | Drift | Volatility | Behavior |
|--------|------|--------|-------------|-------|------------|----------|
| SYNTH | Synthetic Corp | Technology | $150 | 5% | 20% | Balanced growth |
| TECH | Tech Innovations | Technology | $320 | 8% | 30% | High growth, high volatility |
| FINANCE | Finance Holdings | Finance | $85 | 3% | 15% | Stable, low volatility |
| ENERGY | Energy Solutions | Energy | $65 | 2% | 25% | Commodity-like behavior |
| HEALTH | Healthcare Partners | Healthcare | $180 | 6% | 18% | Moderate growth |


## Useful Commands

### View Logs
```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f api
docker-compose logs -f generator
docker-compose logs -f processor
```

### Restart Services
```bash
./stop.sh && ./start.sh
```

### Complete Reset (Remove All Data)
```bash
docker-compose down -v
./start.sh
```

### Check Service Status
```bash
docker-compose ps
```

### Access Database
```bash
docker-compose exec postgres psql -U postgres -d synthetic_market
```

## Development

### Adding New Tickers

Edit `python_src/services/data_generator.py` and add to `TICKER_CONFIGS`:

```python
"NEWTICKER": {
    "start_price": 100.0,
    "drift": 0.05,      # 5% annual return
    "volatility": 0.2,  # 20% volatility
    "min_price": 10,
    "max_price": 1000
}
```

Then add to `.env`:
```

### Database Access

Connect to TimescaleDB:
```bash
docker-compose -f docker-compose.python.yml exec timescaledb psql -U postgres -d synthetic_market
```

## Performance

- **Data Generation**: 10 ticks/second per ticker (configurable)
- **Storage**: TimescaleDB with automatic compression and retention
- **API**: Async FastAPI with high concurrency
- **WebSocket**: Unlimited real-time connections (within server capacity)
- **Data Retention**: 30 days (configurable)