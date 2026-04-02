"""Application configuration using environment variables"""

import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # Server
    PORT = int(os.getenv("PORT", 3000))
    HOST = os.getenv("HOST", "0.0.0.0")

    # Database
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = int(os.getenv("DB_PORT", 5432))
    DB_NAME = os.getenv("DB_NAME", "synthetic_market")
    DB_USER = os.getenv("DB_USER", "postgres")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")

    @property
    def DATABASE_URL(self):
        return f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    @property
    def ASYNC_DATABASE_URL(self):
        return f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    # Kafka
    KAFKA_BROKERS = os.getenv("KAFKA_BROKERS", "localhost:9092").split(",")
    KAFKA_CLIENT_ID = os.getenv("KAFKA_CLIENT_ID", "synthetic-market-api")
    KAFKA_TOPIC_TICKS = os.getenv("KAFKA_TOPIC_TICKS", "market-ticks")
    KAFKA_TOPIC_BARS = os.getenv("KAFKA_TOPIC_BARS", "market-bars")

    # Data Generation
    GENERATOR_INTERVAL_MS = int(os.getenv("GENERATOR_INTERVAL_MS", 100))
    TICKERS = os.getenv("TICKERS", "SYNTH,TECH,FINANCE,ENERGY,HEALTH").split(",")

    # Rate Limiting
    RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
    RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", 100))
    RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", 60))  # seconds

    # Logging
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    # Authentication
    API_KEY_ENABLED = os.getenv("API_KEY_ENABLED", "true").lower() == "true"
    API_KEYS = [k.strip() for k in os.getenv("API_KEYS", "").split(",") if k.strip()]
    if API_KEY_ENABLED and len(API_KEYS) == 0:
        raise ValueError("API_KEYS is not set in .env")

    # Cache
    CACHE_ENABLED = os.getenv("CACHE_ENABLED", "true").lower() == "true"
    CACHE_MAX_SIZE_MB = int(os.getenv("CACHE_MAX_SIZE_MB", 128))
    CACHE_QUOTE_TTL = int(os.getenv("CACHE_QUOTE_TTL", 2))  # seconds
    CACHE_STATS_TTL = int(os.getenv("CACHE_STATS_TTL", 30))  # seconds
    CACHE_TICKERS_TTL = int(os.getenv("CACHE_TICKERS_TTL", 600))  # seconds (10 min)

settings = Settings()
