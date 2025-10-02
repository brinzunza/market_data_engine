"""Data Processor Service - Consumes ticks from Kafka and stores in TimescaleDB"""

import asyncio
import json
import logging
import signal
from datetime import datetime
from aiokafka import AIOKafkaConsumer
from ..config.settings import settings
from ..config.database import db_pool

logger = logging.getLogger(__name__)


class DataProcessorService:
    def __init__(self):
        self.consumer = None
        self.is_running = False
        self.batch_size = 100
        self.batch_timeout = 1.0  # 1 second
        self.tick_buffer = []
        self.last_flush = asyncio.get_event_loop().time()

    async def start(self):
        """Start the data processor service"""
        try:
            # Connect Kafka consumer
            self.consumer = AIOKafkaConsumer(
                settings.KAFKA_TOPIC_TICKS,
                bootstrap_servers=settings.KAFKA_BROKERS,
                group_id="market-data-processor",
                value_deserializer=lambda m: json.loads(m.decode('utf-8')),
                auto_offset_reset='latest',
                enable_auto_commit=True
            )

            await self.consumer.start()
            logger.info("Kafka consumer connected and subscribed to ticks")

            self.is_running = True

            # Start periodic flush task
            flush_task = asyncio.create_task(self.periodic_flush())

            # Start consuming messages
            try:
                async for message in self.consumer:
                    if not self.is_running:
                        break

                    try:
                        tick = message.value
                        await self.process_tick(tick)
                    except Exception as e:
                        logger.error(f"Error processing message: {e}")

            finally:
                flush_task.cancel()

        except Exception as e:
            logger.error(f"Failed to start data processor: {e}")
            raise
        finally:
            await self.stop()

    async def process_tick(self, tick):
        """Process a single tick"""
        try:
            self.tick_buffer.append(tick)

            # Flush if batch size reached
            if len(self.tick_buffer) >= self.batch_size:
                await self.flush_ticks()

        except Exception as e:
            logger.error(f"Error processing tick: {e}")

    async def flush_ticks(self):
        """Flush buffered ticks to database"""
        if not self.tick_buffer:
            return

        conn = None
        try:
            ticks = self.tick_buffer.copy()
            self.tick_buffer.clear()

            conn = db_pool.get_connection()
            cursor = conn.cursor()

            # Build bulk insert query
            values = []
            for tick in ticks:
                timestamp = datetime.fromtimestamp(tick["timestamp"] / 1000.0)
                values.append((
                    timestamp,
                    tick["ticker"],
                    tick["price"],
                    tick["volume"],
                    tick["bid"],
                    tick["ask"]
                ))

            # Execute batch insert
            cursor.executemany(
                """INSERT INTO market_ticks (time, ticker, price, volume, bid, ask)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                values
            )

            conn.commit()
            cursor.close()

            logger.info(f"Flushed {len(ticks)} ticks to database")
            self.last_flush = asyncio.get_event_loop().time()

        except Exception as e:
            logger.error(f"Error flushing ticks to database: {e}")
            if conn:
                conn.rollback()
            # Put ticks back in buffer on error
            self.tick_buffer = ticks + self.tick_buffer
        finally:
            if conn:
                db_pool.return_connection(conn)

    async def periodic_flush(self):
        """Periodically flush buffered ticks"""
        try:
            while self.is_running:
                await asyncio.sleep(self.batch_timeout)

                time_since_last_flush = asyncio.get_event_loop().time() - self.last_flush

                if time_since_last_flush >= self.batch_timeout and self.tick_buffer:
                    await self.flush_ticks()

        except asyncio.CancelledError:
            # Flush remaining ticks before stopping
            await self.flush_ticks()

    async def stop(self):
        """Stop the data processor service"""
        logger.info("Stopping data processor")
        self.is_running = False

        # Flush remaining ticks
        await self.flush_ticks()

        if self.consumer:
            await self.consumer.stop()

        logger.info("Data processor stopped")


async def main():
    """Main entry point for data processor"""
    # Setup signal handlers for graceful shutdown
    processor = DataProcessorService()

    def signal_handler(sig, frame):
        logger.info("Received shutdown signal")
        asyncio.create_task(processor.stop())

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # Start processor
    try:
        await processor.start()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    finally:
        await processor.stop()


if __name__ == "__main__":
    # Setup logging
    from ..config.logger import setup_logger
    setup_logger()

    # Run the processor
    asyncio.run(main())
