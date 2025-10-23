"""Main API Server - FastAPI application with REST and WebSocket endpoints"""

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from typing import Dict, List
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from uuid import uuid4
from .routes.market_data import router as market_data_router
from .routes.websocket import websocket_endpoint, ws_manager
from .config.logger import setup_logger
from .config.settings import settings

# Setup logging
setup_logger()
logger = logging.getLogger(__name__)


class SimpleRateLimiter:
    def __init__(self):
        self.requests: Dict[str, List[float]] = {}

    def is_allowed(self, client_ip: str) -> tuple[bool, int, int]:
        if not settings.RATE_LIMIT_ENABLED:
            return True, settings.RATE_LIMIT_REQUESTS, 0

        now = time.time()
        window_start = now - settings.RATE_LIMIT_WINDOW

        if client_ip not in self.requests:
            self.requests[client_ip] = []

        self.requests[client_ip] = [ts for ts in self.requests[client_ip] if ts > window_start]

        if len(self.requests[client_ip]) >= settings.RATE_LIMIT_REQUESTS:
            retry_after = int(self.requests[client_ip][0] + settings.RATE_LIMIT_WINDOW - now) + 1
            return False, 0, retry_after

        self.requests[client_ip].append(now)
        return True, settings.RATE_LIMIT_REQUESTS - len(self.requests[client_ip]), 0


rate_limiter = SimpleRateLimiter()


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Middleware to validate API key for protected endpoints"""
    async def dispatch(self, request: Request, call_next):
        # Public endpoints that don't require API key
        public_paths = ["/health", "/", "/docs", "/redoc", "/openapi.json"]

        if request.url.path in public_paths:
            return await call_next(request)

        # Check if API key authentication is enabled
        if not settings.API_KEY_ENABLED:
            return await call_next(request)

        # Get API key from multiple sources (in order of precedence):
        # 1. Header: X-API-Key
        # 2. Header: Authorization
        # 3. Query parameter: api_key
        api_key = request.headers.get("X-API-Key") or request.headers.get("Authorization")

        # If not in headers, check query parameters
        if not api_key:
            api_key = request.query_params.get("api_key")

        # Support both "Bearer token" and direct token format for Authorization header
        if api_key and api_key.startswith("Bearer "):
            api_key = api_key[7:]  # Remove "Bearer " prefix

        # Validate API key
        if not api_key or api_key != settings.API_KEY:
            logger.warning(f"Unauthorized access attempt from {request.client.host if request.client else 'unknown'}")
            return JSONResponse(
                status_code=401,
                content={
                    "error": "Unauthorized",
                    "message": "Invalid or missing API key. Include 'X-API-Key' header or '?api_key=' query parameter with your request."
                },
                headers={"WWW-Authenticate": "ApiKey"}
            )

        return await call_next(request)


class ClientIPMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"
        request.state.client_ip = client_ip

        if request.url.path in ["/health", "/ws", "/"]:
            return await call_next(request)

        is_allowed, remaining, retry_after = rate_limiter.is_allowed(client_ip)

        if not is_allowed:
            return JSONResponse(
                status_code=429,
                content={"error": "Rate limit exceeded", "retry_after": retry_after},
                headers={"Retry-After": str(retry_after)}
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response


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

# Add API key middleware (must be added before rate limiting)
app.add_middleware(APIKeyMiddleware)

# Add client IP middleware (includes rate limiting)
app.add_middleware(ClientIPMiddleware)

# Include routers
app.include_router(market_data_router)


@app.get("/")
async def root():
    """API info endpoint"""
    return {
        "name": "Synthetic Market Data API",
        "version": "1.0.0",
        "description": "Real-time synthetic stock market data with WebSocket and REST endpoints",
        "authentication": {
            "required": settings.API_KEY_ENABLED,
            "method": "API Key",
            "options": [
                "Header: X-API-Key",
                "Header: Authorization (Bearer)",
                "Query Parameter: ?api_key="
            ],
            "note": "Include API key in header or as query parameter. Example: /api/v1/tickers?api_key=brunosapikey"
        },
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
