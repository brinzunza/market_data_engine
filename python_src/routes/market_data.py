"""REST API routes for market data"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from datetime import datetime, timedelta
import logging
from ..config.database import db_pool

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["market-data"])


@router.get("/tickers")
async def get_tickers():
    """Get list of all available tickers"""
    try:
        conn = db_pool.get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM tickers ORDER BY ticker")
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()

        tickers = [dict(zip(columns, row)) for row in rows]

        cursor.close()
        db_pool.return_connection(conn)

        return {"success": True, "data": tickers}
    except Exception as e:
        logger.error(f"Error fetching tickers: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch tickers")


@router.get("/quote/{ticker}")
async def get_quote(ticker: str):
    """Get latest quote for a ticker"""
    try:
        conn = db_pool.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """SELECT * FROM market_ticks
               WHERE ticker = %s
               ORDER BY time DESC
               LIMIT 1""",
            (ticker.upper(),)
        )

        columns = [desc[0] for desc in cursor.description]
        row = cursor.fetchone()

        cursor.close()
        db_pool.return_connection(conn)

        if not row:
            raise HTTPException(status_code=404, detail="Ticker not found")

        quote = dict(zip(columns, row))
        return {"success": True, "data": quote}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching quote: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch quote")


@router.get("/history/{ticker}")
async def get_history(
    ticker: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    limit: int = Query(default=1000, le=10000)
):
    """Get historical tick data"""
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
        raise HTTPException(status_code=500, detail="Failed to fetch historical data")


@router.get("/bars/{ticker}")
async def get_bars(
    ticker: str,
    timeframe: str = Query(default="1m", regex="^(1m|5m|1h|1d)$"),
    start: Optional[str] = None,
    end: Optional[str] = None,
    limit: int = Query(default=500, le=5000)
):
    """Get OHLCV bars using aggregation"""
    try:
        start_time = datetime.fromisoformat(start) if start else datetime.now() - timedelta(days=1)
        end_time = datetime.fromisoformat(end) if end else datetime.now()

        interval_map = {
            "1m": "1 minute",
            "5m": "5 minutes",
            "1h": "1 hour",
            "1d": "1 day"
        }
        interval = interval_map[timeframe]

        conn = db_pool.get_connection()
        cursor = conn.cursor()

        # Use standard PostgreSQL date_trunc for time bucketing
        # Use subqueries with ROW_NUMBER() for first/last values
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
        raise HTTPException(status_code=500, detail="Failed to fetch bar data")


@router.get("/stats/{ticker}")
async def get_stats(
    ticker: str,
    period: str = Query(default="1d", regex="^(1h|1d|7d|30d)$")
):
    """Get statistics for a ticker"""
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
            (ticker.upper(), interval, ticker.upper(), interval, ticker.upper(), interval)
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

        return {"success": True, "data": stats}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch statistics")
