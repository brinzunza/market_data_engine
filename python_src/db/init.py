"""Database Initialization Script - Sets up simple PostgreSQL schema"""

import logging
import psycopg2
from ..config.settings import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def initialize_database():
    """Initialize database schema with standard PostgreSQL tables"""
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

        # Create index on ticker and time for faster queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_market_ticks_ticker_time
            ON market_ticks (ticker, time DESC);
        """)
        logger.info("Index on market_ticks created")

        # Create composite index for common query patterns
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_market_ticks_time
            ON market_ticks (time DESC);
        """)
        logger.info("Time index on market_ticks created")

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
