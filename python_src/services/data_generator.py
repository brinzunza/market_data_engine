"""Data Generator Service - Generates synthetic market data using GBM"""

import asyncio
import json
import logging
import signal
from aiokafka import AIOKafkaProducer
from ..config.settings import settings
from ..models.gbm_generator import GBMGenerator

logger = logging.getLogger(__name__)


# Ticker configurations
TICKER_CONFIGS = {
    "SYNTH": {
        "start_price": 150.0,
        "drift": 0.05,      # 5% annual drift
        "volatility": 0.2,  # 20% volatility
        "min_price": 10,
        "max_price": 1000
    },
    "TECH": {
        "start_price": 320.0,
        "drift": 0.08,      # 8% annual drift (high growth)
        "volatility": 0.3,  # 30% volatility (high volatility)
        "min_price": 50,
        "max_price": 2000
    },
    "FINANCE": {
        "start_price": 85.0,
        "drift": 0.03,      # 3% annual drift (stable)
        "volatility": 0.15, # 15% volatility (low volatility)
        "min_price": 20,
        "max_price": 500
    },
    "ENERGY": {
        "start_price": 65.0,
        "drift": 0.02,      # 2% annual drift
        "volatility": 0.25, # 25% volatility (commodity-like)
        "min_price": 10,
        "max_price": 300
    },
    "HEALTH": {
        "start_price": 180.0,
        "drift": 0.06,      # 6% annual drift
        "volatility": 0.18, # 18% volatility
        "min_price": 30,
        "max_price": 800
    }
}


class DataGeneratorService:
    def __init__(self):
        self.generators = {}
        self.producer = None
        self.is_running = False
        self.interval = settings.GENERATOR_INTERVAL_MS / 1000.0  # Convert to seconds

        # Initialize generators for configured tickers
        for ticker in settings.TICKERS:
            ticker = ticker.strip()
            config = TICKER_CONFIGS.get(ticker)
            if config:
                self.generators[ticker] = GBMGenerator(
                    ticker=ticker,
                    start_price=config["start_price"],
                    drift=config["drift"],
                    volatility=config["volatility"],
                    min_price=config["min_price"],
                    max_price=config["max_price"]
                )
                logger.info(f"Initialized generator for {ticker}")

    async def start(self):
        """Start the data generator service"""
        try:
            # Connect Kafka producer
            self.producer = AIOKafkaProducer(
                bootstrap_servers=settings.KAFKA_BROKERS,
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                key_serializer=lambda k: k.encode('utf-8') if k else None
            )

            await self.producer.start()
            logger.info("Kafka producer connected")

            self.is_running = True
            logger.info(f"Starting data generation with {self.interval}s interval")

            # Start generation loop
            await self.generation_loop()

        except Exception as e:
            logger.error(f"Failed to start data generator: {e}")
            raise
        finally:
            await self.stop()

    async def generation_loop(self):
        """Main generation loop"""
        tick_count = 0

        while self.is_running:
            start_time = asyncio.get_event_loop().time()

            try:
                # Generate ticks for all tickers
                tasks = []

                for ticker, generator in self.generators.items():
                    tick = generator.generate_tick()

                    # Send to Kafka
                    task = self.producer.send(
                        settings.KAFKA_TOPIC_TICKS,
                        key=ticker,
                        value=tick
                    )
                    tasks.append(task)

                # Wait for all sends to complete
                await asyncio.gather(*tasks)

                tick_count += len(self.generators)

                # Log every 10 seconds
                if tick_count % (10 * len(self.generators) * (1000 / settings.GENERATOR_INTERVAL_MS)) < len(self.generators):
                    logger.info(f"Generated {len(self.generators)} ticks")

            except Exception as e:
                logger.error(f"Error in generation loop: {e}")

            # Wait for next interval
            elapsed = asyncio.get_event_loop().time() - start_time
            wait_time = max(0, self.interval - elapsed)
            await asyncio.sleep(wait_time)

    async def stop(self):
        """Stop the data generator service"""
        logger.info("Stopping data generator")
        self.is_running = False

        if self.producer:
            await self.producer.stop()

        logger.info("Data generator stopped")


async def main():
    """Main entry point for data generator"""
    # Setup signal handlers for graceful shutdown
    generator = DataGeneratorService()

    def signal_handler(sig, frame):
        logger.info("Received shutdown signal")
        asyncio.create_task(generator.stop())

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # Start generator
    try:
        await generator.start()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    finally:
        await generator.stop()


if __name__ == "__main__":
    # Setup logging
    from ..config.logger import setup_logger
    setup_logger()

    # Run the generator
    asyncio.run(main())
