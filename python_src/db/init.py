"""Database Initialization Script - Sets up TimescaleDB schema and hypertables"""

import logging
import psycopg2
from ..config.settings import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def initialize_database():
    """Initialize database schema and TimescaleDB hypertables"""
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

        logger.info("Starting database initialization...")

        # Enable TimescaleDB extension
        cursor.execute("CREATE EXTENSION IF NOT EXISTS timescaledb;")
        logger.info("TimescaleDB extension enabled")

        # Create tickers metadata table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tickers (
                ticker VARCHAR(20) PRIMARY KEY,
                name VARCHAR(100),
                sector VARCHAR(50),
                initial_price DECIMAL(10, 2),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        logger.info("Tickers table created")

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
        logger.info("Market ticks table created")

        # Convert to hypertable (TimescaleDB feature for time-series optimization)
        cursor.execute("""
            SELECT create_hypertable('market_ticks', 'time',
                if_not_exists => TRUE,
                chunk_time_interval => INTERVAL '1 day'
            );
        """)
        logger.info("Market ticks hypertable created")

        # Create index on ticker for faster queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_market_ticks_ticker_time
            ON market_ticks (ticker, time DESC);
        """)
        logger.info("Index on market_ticks created")

        # Create OHLCV bars table (aggregated data)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS market_bars (
                time TIMESTAMPTZ NOT NULL,
                ticker VARCHAR(20) NOT NULL,
                timeframe VARCHAR(10) NOT NULL,
                open DECIMAL(10, 2) NOT NULL,
                high DECIMAL(10, 2) NOT NULL,
                low DECIMAL(10, 2) NOT NULL,
                close DECIMAL(10, 2) NOT NULL,
                volume BIGINT NOT NULL,
                PRIMARY KEY (time, ticker, timeframe)
            );
        """)
        logger.info("Market bars table created")

        # Convert to hypertable
        cursor.execute("""
            SELECT create_hypertable('market_bars', 'time',
                if_not_exists => TRUE,
                chunk_time_interval => INTERVAL '7 days'
            );
        """)
        logger.info("Market bars hypertable created")

        # Create index on bars
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_market_bars_ticker_timeframe_time
            ON market_bars (ticker, timeframe, time DESC);
        """)
        logger.info("Index on market_bars created")

        # Insert sample ticker metadata
        cursor.execute("""
            INSERT INTO tickers (ticker, name, sector, initial_price)
            VALUES
                ('SYNTH', 'Synthetic Corp', 'Technology', 150.00),
                ('TECH', 'Tech Innovations Inc', 'Technology', 320.00),
                ('FINANCE', 'Finance Holdings', 'Finance', 85.00),
                ('ENERGY', 'Energy Solutions', 'Energy', 65.00),
                ('HEALTH', 'Healthcare Partners', 'Healthcare', 180.00)
            ON CONFLICT (ticker) DO NOTHING;
        """)
        logger.info("Sample ticker data inserted")

        # Create continuous aggregate for 1-minute bars (materialized view)
        cursor.execute("""
            CREATE MATERIALIZED VIEW IF NOT EXISTS market_bars_1min
            WITH (timescaledb.continuous) AS
            SELECT
                time_bucket('1 minute', time) AS time,
                ticker,
                '1m' as timeframe,
                FIRST(price, time) as open,
                MAX(price) as high,
                MIN(price) as low,
                LAST(price, time) as close,
                SUM(volume)::BIGINT as volume
            FROM market_ticks
            GROUP BY time_bucket('1 minute', time), ticker
            WITH NO DATA;
        """)
        logger.info("1-minute continuous aggregate created")

        # Add continuous aggregate policy (refresh every minute)
        cursor.execute("""
            SELECT add_continuous_aggregate_policy('market_bars_1min',
                start_offset => INTERVAL '1 hour',
                end_offset => INTERVAL '1 minute',
                schedule_interval => INTERVAL '1 minute',
                if_not_exists => TRUE
            );
        """)
        logger.info("Continuous aggregate policy added")

        # Create retention policy to drop old data after 30 days
        cursor.execute("""
            SELECT add_retention_policy('market_ticks', INTERVAL '30 days', if_not_exists => TRUE);
        """)
        logger.info("Retention policy added")

        logger.info("Database initialization completed successfully")

        cursor.close()

    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        raise
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    initialize_database()
