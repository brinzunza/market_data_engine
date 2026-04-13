"""Database Initialization Script - Sets up TimescaleDB with hypertables and continuous aggregates"""

import logging
import psycopg2
from ..config.settings import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def initialize_database():
    """Initialize database schema with TimescaleDB features"""
    conn = None

    try:
        # Connect to database
        conn = psycopg2.connect(
            host=settings.DB_HOST,
            port=settings.DB_PORT,
            database=settings.DB_NAME,
            user=settings.DB_USER,
            password=settings.DB_PASSWORD
        )
        conn.autocommit = True
        cursor = conn.cursor()

        logger.info("Starting TimescaleDB initialization...")

        # Enable TimescaleDB extension
        cursor.execute("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;")
        logger.info("✓ TimescaleDB extension enabled")

        # Create tickers metadata table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tickers (
                id SERIAL PRIMARY KEY,
                ticker VARCHAR(20) UNIQUE NOT NULL,
                name VARCHAR(100),
                sector VARCHAR(50),
                initial_price DECIMAL(10, 2),
                min_price DECIMAL(10, 2),
                max_price DECIMAL(10, 2),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        logger.info("✓ Tickers table created")

        # Create market_ticks table (time-series data)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS market_ticks (
                time TIMESTAMPTZ NOT NULL,
                ticker VARCHAR(20) NOT NULL,
                price DECIMAL(10, 2) NOT NULL,
                volume INTEGER NOT NULL,
                bid DECIMAL(10, 2),
                ask DECIMAL(10, 2)
            );
        """)
        logger.info("✓ Market ticks table created")

        # Convert to hypertable (partitioned by time with 1-day chunks)
        try:
            cursor.execute("""
                SELECT create_hypertable(
                    'market_ticks',
                    'time',
                    chunk_time_interval => INTERVAL '1 day',
                    if_not_exists => TRUE
                );
            """)
            logger.info("✓ Market ticks converted to hypertable (1-day chunks)")
        except Exception as e:
            if "already a hypertable" in str(e):
                logger.info("✓ Market ticks is already a hypertable")
            else:
                raise

        # Create indexes on hypertable (AFTER hypertable creation)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_market_ticks_ticker_time
            ON market_ticks (ticker, time DESC);
        """)
        logger.info("✓ Index on (ticker, time) created")

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_market_ticks_time
            ON market_ticks (time DESC);
        """)
        logger.info("✓ Index on time created")

        # Enable compression (compress chunks older than 1 day)
        cursor.execute("""
            ALTER TABLE market_ticks SET (
                timescaledb.compress,
                timescaledb.compress_segmentby = 'ticker',
                timescaledb.compress_orderby = 'time DESC'
            );
        """)
        logger.info("✓ Compression settings configured")

        # Add compression policy
        try:
            cursor.execute("""
                SELECT add_compression_policy(
                    'market_ticks',
                    INTERVAL '1 day'
                );
            """)
            logger.info("✓ Compression policy added (compress after 1 day)")
        except Exception as e:
            if "already exists" in str(e):
                logger.info("✓ Compression policy already exists")
            else:
                raise

        # Add data retention policy (delete raw ticks older than 90 days)
        try:
            cursor.execute("""
                SELECT add_retention_policy(
                    'market_ticks',
                    INTERVAL '90 days'
                );
            """)
            logger.info("✓ Retention policy added (delete after 90 days)")
        except Exception as e:
            if "already exists" in str(e):
                logger.info("✓ Retention policy already exists")
            else:
                raise

        # Create continuous aggregate: 1-second OHLC bars
        cursor.execute("""
            CREATE MATERIALIZED VIEW IF NOT EXISTS market_ohlc_1s
            WITH (timescaledb.continuous) AS
            SELECT
                time_bucket('1 second', time) AS bucket,
                ticker,
                FIRST(price, time) AS open,
                MAX(price) AS high,
                MIN(price) AS low,
                LAST(price, time) AS close,
                SUM(volume) AS volume,
                COUNT(*) AS tick_count
            FROM market_ticks
            GROUP BY bucket, ticker
            WITH NO DATA;
        """)
        logger.info("✓ Continuous aggregate created: market_ohlc_1s")

        # Add refresh policy for 1-second bars
        try:
            cursor.execute("""
                SELECT add_continuous_aggregate_policy(
                    'market_ohlc_1s',
                    start_offset => INTERVAL '1 hour',
                    end_offset => INTERVAL '5 seconds',
                    schedule_interval => INTERVAL '5 seconds'
                );
            """)
            logger.info("✓ Refresh policy added for 1s bars (every 5 seconds)")
        except Exception as e:
            if "already exists" in str(e):
                logger.info("✓ Refresh policy already exists for 1s bars")
            else:
                raise

        # Create continuous aggregate: 1-minute OHLC bars
        cursor.execute("""
            CREATE MATERIALIZED VIEW IF NOT EXISTS market_ohlc_1m
            WITH (timescaledb.continuous) AS
            SELECT
                time_bucket('1 minute', time) AS bucket,
                ticker,
                FIRST(price, time) AS open,
                MAX(price) AS high,
                MIN(price) AS low,
                LAST(price, time) AS close,
                SUM(volume) AS volume,
                COUNT(*) AS tick_count
            FROM market_ticks
            GROUP BY bucket, ticker
            WITH NO DATA;
        """)
        logger.info("✓ Continuous aggregate created: market_ohlc_1m")

        # Add refresh policy for 1-minute bars
        try:
            cursor.execute("""
                SELECT add_continuous_aggregate_policy(
                    'market_ohlc_1m',
                    start_offset => INTERVAL '2 hours',
                    end_offset => INTERVAL '10 seconds',
                    schedule_interval => INTERVAL '10 seconds'
                );
            """)
            logger.info("✓ Refresh policy added for 1m bars (every 10 seconds)")
        except Exception as e:
            if "already exists" in str(e):
                logger.info("✓ Refresh policy already exists for 1m bars")
            else:
                raise

        # Create continuous aggregate: 5-minute OHLC bars
        cursor.execute("""
            CREATE MATERIALIZED VIEW IF NOT EXISTS market_ohlc_5m
            WITH (timescaledb.continuous) AS
            SELECT
                time_bucket('5 minutes', time) AS bucket,
                ticker,
                FIRST(price, time) AS open,
                MAX(price) AS high,
                MIN(price) AS low,
                LAST(price, time) AS close,
                SUM(volume) AS volume,
                COUNT(*) AS tick_count
            FROM market_ticks
            GROUP BY bucket, ticker
            WITH NO DATA;
        """)
        logger.info("✓ Continuous aggregate created: market_ohlc_5m")

        # Add refresh policy for 5-minute bars
        try:
            cursor.execute("""
                SELECT add_continuous_aggregate_policy(
                    'market_ohlc_5m',
                    start_offset => INTERVAL '6 hours',
                    end_offset => INTERVAL '30 seconds',
                    schedule_interval => INTERVAL '30 seconds'
                );
            """)
            logger.info("✓ Refresh policy added for 5m bars (every 30 seconds)")
        except Exception as e:
            if "already exists" in str(e):
                logger.info("✓ Refresh policy already exists for 5m bars")
            else:
                raise

        # Create continuous aggregate: 1-hour OHLC bars
        cursor.execute("""
            CREATE MATERIALIZED VIEW IF NOT EXISTS market_ohlc_1h
            WITH (timescaledb.continuous) AS
            SELECT
                time_bucket('1 hour', time) AS bucket,
                ticker,
                FIRST(price, time) AS open,
                MAX(price) AS high,
                MIN(price) AS low,
                LAST(price, time) AS close,
                SUM(volume) AS volume,
                COUNT(*) AS tick_count
            FROM market_ticks
            GROUP BY bucket, ticker
            WITH NO DATA;
        """)
        logger.info("✓ Continuous aggregate created: market_ohlc_1h")

        # Add refresh policy for 1-hour bars
        try:
            cursor.execute("""
                SELECT add_continuous_aggregate_policy(
                    'market_ohlc_1h',
                    start_offset => INTERVAL '1 day',
                    end_offset => INTERVAL '1 minute',
                    schedule_interval => INTERVAL '1 minute'
                );
            """)
            logger.info("✓ Refresh policy added for 1h bars (every 1 minute)")
        except Exception as e:
            if "already exists" in str(e):
                logger.info("✓ Refresh policy already exists for 1h bars")
            else:
                raise

        # Insert sample ticker metadata
        cursor.execute("""
            INSERT INTO tickers (ticker, name, sector, initial_price, min_price, max_price)
            VALUES
                ('SYNTH', 'Synthetic Corp', 'Technology', 100.00, 50.00, 200.00),
                ('TECH', 'Tech Industries', 'Technology', 150.00, 75.00, 300.00),
                ('FINANCE', 'Finance Group', 'Finance', 80.00, 40.00, 160.00),
                ('ENERGY', 'Energy Solutions', 'Energy', 120.00, 60.00, 240.00),
                ('HEALTH', 'Health Systems', 'Healthcare', 90.00, 45.00, 180.00)
            ON CONFLICT (ticker) DO NOTHING;
        """)
        logger.info("✓ Sample ticker data inserted")

        logger.info("=" * 60)
        logger.info("TimescaleDB initialization completed successfully!")
        logger.info("=" * 60)
        logger.info("Features enabled:")
        logger.info("  - Hypertable with 1-day chunks")
        logger.info("  - Compression after 1 day (95% storage savings)")
        logger.info("  - Data retention: 90 days (auto-delete old data)")
        logger.info("  - Continuous aggregates: 1s, 1m, 5m, 1h OHLC bars")
        logger.info("  - Auto-refresh policies for real-time aggregates")
        logger.info("=" * 60)

        cursor.close()

    except Exception as e:
        logger.error(f"Error initializing TimescaleDB: {e}")
        raise
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    initialize_database()
