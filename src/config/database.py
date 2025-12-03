"""Database connection configuration"""

import psycopg2
from psycopg2 import pool
import logging
from .settings import settings

logger = logging.getLogger(__name__)


class DatabasePool:
    def __init__(self):
        try:
            self.connection_pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=5,
                maxconn=20,
                host=settings.DB_HOST,
                port=settings.DB_PORT,
                database=settings.DB_NAME,
                user=settings.DB_USER,
                password=settings.DB_PASSWORD
            )
            logger.info("Database connection pool created successfully")
        except Exception as e:
            logger.error(f"Error creating database connection pool: {e}")
            raise

    def get_connection(self):
        """Get a connection from the pool"""
        return self.connection_pool.getconn()

    def return_connection(self, connection):
        """Return a connection to the pool"""
        self.connection_pool.putconn(connection)

    def close_all_connections(self):
        """Close all connections in the pool"""
        self.connection_pool.closeall()
        logger.info("All database connections closed")


# Global database pool instance
db_pool = DatabasePool()


def get_db_connection():
    """Context manager for database connections"""
    connection = db_pool.get_connection()
    try:
        yield connection
    finally:
        db_pool.return_connection(connection)
