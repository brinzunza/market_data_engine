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


settings = Settings()
