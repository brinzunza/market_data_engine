"""Main API Server - FastAPI application with REST and WebSocket endpoints"""

import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from uuid import uuid4
from .routes.market_data import router as market_data_router
from .routes.websocket import websocket_endpoint, ws_manager
from .config.logger import setup_logger

# Setup logging
setup_logger()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan events for startup and shutdown"""
    # Startup
    logger.info("Starting Synthetic Market Data API")

    # Start WebSocket Kafka consumer in background
    asyncio.create_task(ws_manager.start_kafka_consumer())

    yield

    # Shutdown
    logger.info("Shutting down Synthetic Market Data API")
    await ws_manager.shutdown()


# Create FastAPI app
app = FastAPI(
    title="Synthetic Market Data API",
    version="1.0.0",
    description="Real-time synthetic stock market data with WebSocket and REST endpoints",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(market_data_router)


@app.get("/")
async def root():
    """API info endpoint"""
    return {
        "name": "Synthetic Market Data API",
        "version": "1.0.0",
        "description": "Real-time synthetic stock market data with WebSocket and REST endpoints",
        "endpoints": {
            "rest": {
                "tickers": "GET /api/v1/tickers",
                "quote": "GET /api/v1/quote/:ticker",
                "history": "GET /api/v1/history/:ticker",
                "bars": "GET /api/v1/bars/:ticker",
                "stats": "GET /api/v1/stats/:ticker"
            },
            "websocket": {
                "url": "/ws",
                "protocol": "ws",
                "description": "Real-time market data streaming"
            }
        },
        "documentation": "https://github.com/brinzunza/market_data_engine"
    }


@app.get("/health")
async def health():
    """Health check endpoint"""
    import time
    return {
        "status": "healthy",
        "timestamp": time.time(),
    }


@app.websocket("/ws")
async def websocket_route(websocket):
    """WebSocket endpoint for real-time market data"""
    client_id = str(uuid4())
    await websocket_endpoint(websocket, client_id)


if __name__ == "__main__":
    import uvicorn
    from .config.settings import settings

    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=False,
        log_level=settings.LOG_LEVEL.lower()
    )
