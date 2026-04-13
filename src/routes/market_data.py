"""REST API routes for market data"""

import time as _time
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from datetime import datetime, timedelta
import logging
from ..config.database import db_pool
from ..monitoring.collector import metrics
from ..config.settings import settings
from ..cache import get_cache

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["market-data"])


@router.get("/tickers")
async def get_tickers():
    """Get list of all available tickers"""
    _start = _time.time()
    cache_key = "tickers:all"

    # Try cache first
    if settings.CACHE_ENABLED:
        cache = get_cache()
        cached_data = cache.get(cache_key)
        if cached_data is not None:
            metrics.counter("api.requests")
            metrics.counter("cache.hits")
            metrics.histogram("api.request_latency_ms", (_time.time() - _start) * 1000)
            logger.debug("Cache hit for /tickers")
            return cached_data
        metrics.counter("cache.misses")

    # Cache miss - query database
    try:
        conn = db_pool.get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM tickers ORDER BY ticker")
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()

        tickers = [dict(zip(columns, row)) for row in rows]

        cursor.close()
        db_pool.return_connection(conn)

        result = {"success": True, "data": tickers}

        # Store in cache
        if settings.CACHE_ENABLED:
            cache.set(cache_key, result, settings.CACHE_TICKERS_TTL)
            logger.debug(f"Cached /tickers with TTL={settings.CACHE_TICKERS_TTL}s")

        metrics.counter("api.requests")
        metrics.histogram("api.request_latency_ms", (_time.time() - _start) * 1000)
        return result
    except Exception as e:
        logger.error(f"Error fetching tickers: {e}")
        metrics.counter("api.errors")
        metrics.histogram("api.request_latency_ms", (_time.time() - _start) * 1000)
        raise HTTPException(status_code=500, detail="Failed to fetch tickers")


@router.get("/quote/{ticker}")
async def get_quote(ticker: str):
    """Get latest quote for a ticker"""
    _start = _time.time()
    ticker_upper = ticker.upper()
    cache_key = f"quote:{ticker_upper}"

    # Try cache first
    if settings.CACHE_ENABLED:
        cache = get_cache()
        cached_data = cache.get(cache_key)
        if cached_data is not None:
            metrics.counter("api.requests")
            metrics.counter("cache.hits")
            metrics.histogram("api.request_latency_ms", (_time.time() - _start) * 1000)
            logger.debug(f"Cache hit for /quote/{ticker_upper}")
            return cached_data
        metrics.counter("cache.misses")

    # Cache miss - query database
    try:
        conn = db_pool.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """SELECT * FROM market_ticks
               WHERE ticker = %s
               ORDER BY time DESC
               LIMIT 1""",
            (ticker_upper,)
        )

        columns = [desc[0] for desc in cursor.description]
        row = cursor.fetchone()

        cursor.close()
        db_pool.return_connection(conn)

        if not row:
            metrics.counter("api.errors")
            raise HTTPException(status_code=404, detail="Ticker not found")

        quote = dict(zip(columns, row))
        result = {"success": True, "data": quote}

        # Store in cache with short TTL (quote data changes frequently)
        if settings.CACHE_ENABLED:
            cache.set(cache_key, result, settings.CACHE_QUOTE_TTL)
            logger.debug(f"Cached /quote/{ticker_upper} with TTL={settings.CACHE_QUOTE_TTL}s")

        metrics.counter("api.requests")
        metrics.histogram("api.request_latency_ms", (_time.time() - _start) * 1000)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching quote: {e}")
        metrics.counter("api.errors")
        metrics.histogram("api.request_latency_ms", (_time.time() - _start) * 1000)
        raise HTTPException(status_code=500, detail="Failed to fetch quote")


@router.get("/history/{ticker}")
async def get_history(
    ticker: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    limit: int = Query(default=1000, le=10000)
):
    """Get historical tick data"""
    _start = _time.time()
    try:
        start_time = datetime.fromisoformat(start) if start else datetime.now() - timedelta(hours=1)
        end_time = datetime.fromisoformat(end) if end else datetime.now()

        conn = db_pool.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """SELECT time, ticker, price, volume, bid, ask
               FROM market_ticks
               WHERE ticker = %s
                 AND time >= %s
                 AND time <= %s
               ORDER BY time ASC
               LIMIT %s""",
            (ticker.upper(), start_time, end_time, limit)
        )

        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()

        ticks = [dict(zip(columns, row)) for row in rows]

        cursor.close()
        db_pool.return_connection(conn)

        metrics.counter("api.requests")
        metrics.histogram("api.request_latency_ms", (_time.time() - _start) * 1000)
        return {
            "success": True,
            "data": ticks,
            "meta": {
                "ticker": ticker.upper(),
                "start": start_time.isoformat(),
                "end": end_time.isoformat(),
                "count": len(ticks)
            }
        }
    except Exception as e:
        logger.error(f"Error fetching history: {e}")
        metrics.counter("api.errors")
        metrics.histogram("api.request_latency_ms", (_time.time() - _start) * 1000)
        raise HTTPException(status_code=500, detail="Failed to fetch historical data")


@router.get("/bars/{ticker}")
async def get_bars(
    ticker: str,
    timeframe: str = Query(default="1m", regex="^(1s|1m|5m|1h|1d)$"),
    start: Optional[str] = None,
    end: Optional[str] = None,
    limit: int = Query(default=500, le=5000)
):
    """Get OHLCV bars using TimescaleDB continuous aggregates (10-100x faster!)"""
    _start = _time.time()
    try:
        start_time = datetime.fromisoformat(start) if start else datetime.now() - timedelta(days=1)
        end_time = datetime.fromisoformat(end) if end else datetime.now()

        # Map timeframe to continuous aggregate view
        aggregate_map = {
            "1s": "market_ohlc_1s",
            "1m": "market_ohlc_1m",
            "5m": "market_ohlc_5m",
            "1h": "market_ohlc_1h"
        }

        conn = db_pool.get_connection()
        cursor = conn.cursor()

        # Use continuous aggregate if available, otherwise fall back to raw data
        if timeframe in aggregate_map:
            view_name = aggregate_map[timeframe]

            # Query pre-computed OHLC bars from continuous aggregate (MUCH faster!)
            cursor.execute(
                f"""SELECT
                     bucket AS time,
                     ticker,
                     %s as timeframe,
                     open,
                     high,
                     low,
                     close,
                     volume
                   FROM {view_name}
                   WHERE ticker = %s
                     AND bucket >= %s
                     AND bucket <= %s
                   ORDER BY bucket DESC
                   LIMIT %s""",
                (timeframe, ticker.upper(), start_time, end_time, limit)
            )
        else:
            # For 1d bars, aggregate on-demand from raw ticks
            interval = "1 day"
            cursor.execute(
                """WITH bucketed_data AS (
                     SELECT
                       date_trunc(%s, time) AS bucket_time,
                       ticker,
                       price,
                       volume,
                       time,
                       ROW_NUMBER() OVER (PARTITION BY date_trunc(%s, time) ORDER BY time ASC) as rn_first,
                       ROW_NUMBER() OVER (PARTITION BY date_trunc(%s, time) ORDER BY time DESC) as rn_last
                     FROM market_ticks
                     WHERE ticker = %s
                       AND time >= %s
                       AND time <= %s
                   )
                   SELECT
                     bucket_time AS time,
                     ticker,
                     %s as timeframe,
                     MAX(CASE WHEN rn_first = 1 THEN price END) as open,
                     MAX(price) as high,
                     MIN(price) as low,
                     MAX(CASE WHEN rn_last = 1 THEN price END) as close,
                     SUM(volume)::BIGINT as volume
                   FROM bucketed_data
                   GROUP BY bucket_time, ticker
               ORDER BY bucket_time ASC
               LIMIT %s""",
            (interval, interval, interval, ticker.upper(), start_time, end_time, timeframe, limit)
        )

        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()

        bars = [dict(zip(columns, row)) for row in rows]

        cursor.close()
        db_pool.return_connection(conn)

        metrics.counter("api.requests")
        metrics.histogram("api.request_latency_ms", (_time.time() - _start) * 1000)
        return {
            "success": True,
            "data": bars,
            "meta": {
                "ticker": ticker.upper(),
                "timeframe": timeframe,
                "start": start_time.isoformat(),
                "end": end_time.isoformat(),
                "count": len(bars)
            }
        }
    except Exception as e:
        logger.error(f"Error fetching bars: {e}")
        metrics.counter("api.errors")
        metrics.histogram("api.request_latency_ms", (_time.time() - _start) * 1000)
        raise HTTPException(status_code=500, detail="Failed to fetch bar data")


@router.get("/stats/{ticker}")
async def get_stats(
    ticker: str,
    period: str = Query(default="1d", regex="^(1h|1d|7d|30d)$")
):
    """Get statistics for a ticker"""
    _start = _time.time()
    ticker_upper = ticker.upper()
    cache_key = f"stats:{ticker_upper}:{period}"

    # Try cache first
    if settings.CACHE_ENABLED:
        cache = get_cache()
        cached_data = cache.get(cache_key)
        if cached_data is not None:
            metrics.counter("api.requests")
            metrics.counter("cache.hits")
            metrics.histogram("api.request_latency_ms", (_time.time() - _start) * 1000)
            logger.debug(f"Cache hit for /stats/{ticker_upper}?period={period}")
            return cached_data
        metrics.counter("cache.misses")

    # Cache miss - query database
    try:
        interval_map = {
            "1h": "1 hour",
            "1d": "1 day",
            "7d": "7 days",
            "30d": "30 days"
        }
        interval = interval_map[period]

        conn = db_pool.get_connection()
        cursor = conn.cursor()

        # Use subqueries to get first and last prices by time
        cursor.execute(
            """SELECT
                 ticker,
                 COUNT(*) as tick_count,
                 MIN(price) as low,
                 MAX(price) as high,
                 (SELECT price FROM market_ticks
                  WHERE ticker = %s AND time >= NOW() - %s::interval
                  ORDER BY time ASC LIMIT 1) as open,
                 (SELECT price FROM market_ticks
                  WHERE ticker = %s AND time >= NOW() - %s::interval
                  ORDER BY time DESC LIMIT 1) as close,
                 AVG(price) as avg_price,
                 SUM(volume)::BIGINT as total_volume,
                 STDDEV(price) as volatility
               FROM market_ticks
               WHERE ticker = %s
                 AND time >= NOW() - %s::interval
               GROUP BY ticker""",
            (ticker_upper, interval, ticker_upper, interval, ticker_upper, interval)
        )

        columns = [desc[0] for desc in cursor.description]
        row = cursor.fetchone()

        cursor.close()
        db_pool.return_connection(conn)

        if not row:
            raise HTTPException(status_code=404, detail="No data found for ticker")

        stats = dict(zip(columns, row))
        change = float(stats["close"]) - float(stats["open"])
        change_pct = (change / float(stats["open"])) * 100

        stats["change"] = round(change, 2)
        stats["change_pct"] = round(change_pct, 2)
        stats["period"] = period

        result = {"success": True, "data": stats}

        # Store in cache (stats are computationally expensive)
        if settings.CACHE_ENABLED:
            cache.set(cache_key, result, settings.CACHE_STATS_TTL)
            logger.debug(f"Cached /stats/{ticker_upper}?period={period} with TTL={settings.CACHE_STATS_TTL}s")

        metrics.counter("api.requests")
        metrics.histogram("api.request_latency_ms", (_time.time() - _start) * 1000)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching stats: {e}")
        metrics.counter("api.errors")
        metrics.histogram("api.request_latency_ms", (_time.time() - _start) * 1000)
        raise HTTPException(status_code=500, detail="Failed to fetch statistics")
