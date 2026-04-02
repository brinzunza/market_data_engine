<div style="margin-bottom: 20px;">
  <img src="phanes.jpg" alt="phanes" width="100%" style="display: block;"/>
</div>

# Synthetic Market Data API

Real-time synthetic stock market data — generated with Geometric Brownian Motion, streamed over Kafka, served via REST and WebSocket.

---

## Setup

Requires Docker Desktop.

```bash
git clone <your-repo-url>
cd synthDataAPI
./start.sh        # starts everything
./stop.sh         # stops everything
```

That launches PostgreSQL, Kafka, the data generator, the data processor, and the API server on port 3000.

---

## API Keys

All `/api/v1/…` endpoints require an API key. Pass it as a header or query parameter:

```bash
curl -H "X-API-Key: brunoinzunza" http://localhost:3000/api/v1/tickers

# or as a query param
curl http://localhost:3000/api/v1/tickers?api_key=brunoinzunza
```

Valid keys are defined in `.env` under `API_KEYS`.

---

## Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/tickers` | List all tickers |
| GET | `/api/v1/quote/:ticker` | Latest price for a ticker |
| GET | `/api/v1/history/:ticker` | Historical ticks (`start`, `end`, `limit`) |
| GET | `/api/v1/bars/:ticker` | OHLCV bars (`timeframe`: 1m/5m/1h/1d) |
| GET | `/api/v1/stats/:ticker` | Stats for a period (`period`: 1h/1d/7d/30d) |
| WS | `/ws` | Real-time tick streaming (see below) |
| GET | `/monitor` | Live monitoring dashboard |
| GET | `/chart` | TradingView-style live price chart |

Public endpoints (no key needed): `/`, `/health`, `/docs`, `/monitor`, `/chart`.

---

## WebSocket

```python
import asyncio, websockets, json

async def main():
    async with websockets.connect("ws://localhost:3000/ws") as ws:
        await ws.recv()                          # welcome message
        await ws.send(json.dumps({
            "type": "subscribe",
            "tickers": ["SYNTH", "TECH"]
        }))
        async for msg in ws:
            print(json.loads(msg))

asyncio.run(main())
```

Messages you receive have `"type": "tick"` with `ticker`, `price`, `volume`, `bid`, `ask`, `timestamp`.

---

## Tickers

| Ticker | Start Price | Drift | Volatility |
|---|---|---|---|
| SYNTH | $150 | 5% | 20% |
| TECH | $320 | 8% | 30% |
| FINANCE | $85 | 3% | 15% |
| ENERGY | $65 | 2% | 25% |
| HEALTH | $180 | 6% | 18% |

---

## Monitoring

Open `http://localhost:3000/monitor` in a browser. Live charts, stat cards, and alerts — no setup required.

---

## Useful commands

```bash
docker-compose logs -f              # all service logs
docker-compose logs -f generator    # single service
docker-compose ps                   # status
docker-compose down -v && ./start.sh  # full reset
```
