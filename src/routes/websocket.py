"""WebSocket handler for real-time market data streaming"""

import asyncio
import json
import logging
from typing import Dict, Set
from fastapi import WebSocket, WebSocketDisconnect
from aiokafka import AIOKafkaConsumer
from ..config.settings import settings
from ..monitoring.collector import metrics

logger = logging.getLogger(__name__)


class WebSocketManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.subscriptions: Dict[str, Set[str]] = {}  # client_id -> set of tickers
        self.tick_cache: Dict[str, dict] = {}
        self.kafka_consumer = None
        self.is_running = False

    def _market_client_count(self) -> int:
        """Count connections that have at least one real ticker subscription.
        Connections that only subscribe to __METRICS__ are internal (dashboard)
        and should not show up in the gauge."""
        count = 0
        for subs in self.subscriptions.values():
            if subs - {"__METRICS__"}:   # non-empty after removing the internal key
                count += 1
        return count

    async def connect(self, websocket: WebSocket, client_id: str):
        """Accept WebSocket connection"""
        await websocket.accept()
        self.active_connections[client_id] = websocket
        self.subscriptions[client_id] = set()

        logger.info(f"WebSocket client connected: {client_id}")

        # Send welcome message
        await self.send_message(websocket, {
            "type": "connected",
            "clientId": client_id,
            "timestamp": asyncio.get_event_loop().time() * 1000
        })

    def disconnect(self, client_id: str):
        """Remove client connection"""
        if client_id in self.active_connections:
            del self.active_connections[client_id]
        if client_id in self.subscriptions:
            del self.subscriptions[client_id]

        # --- monitoring ---
        metrics.gauge("websocket.active_connections", self._market_client_count())

        logger.info(f"WebSocket client disconnected: {client_id}")

    async def send_message(self, websocket: WebSocket, message: dict):
        """Send JSON message to client"""
        try:
            await websocket.send_text(json.dumps(message))
        except Exception as e:
            logger.error(f"Error sending message: {e}")

    async def handle_message(self, client_id: str, message: dict):
        """Handle incoming client messages"""
        websocket = self.active_connections.get(client_id)
        if not websocket:
            return

        msg_type = message.get("type")

        if msg_type == "subscribe":
            await self.handle_subscribe(client_id, message.get("tickers", []))
        elif msg_type == "unsubscribe":
            await self.handle_unsubscribe(client_id, message.get("tickers", []))
        elif msg_type == "ping":
            await self.send_message(websocket, {
                "type": "pong",
                "timestamp": asyncio.get_event_loop().time() * 1000
            })
        else:
            await self.send_message(websocket, {
                "type": "error",
                "message": "Unknown message type"
            })

    async def handle_subscribe(self, client_id: str, tickers):
        """Handle subscription request"""
        websocket = self.active_connections.get(client_id)
        if not websocket:
            return

        ticker_list = tickers if isinstance(tickers, list) else [tickers]

        for ticker in ticker_list:
            ticker_upper = ticker.upper()
            self.subscriptions[client_id].add(ticker_upper)

            # Send latest cached tick if available
            if ticker_upper in self.tick_cache:
                await self.send_message(websocket, {
                    "type": "tick",
                    "data": self.tick_cache[ticker_upper]
                })

        await self.send_message(websocket, {
            "type": "subscribed",
            "tickers": ticker_list,
            "timestamp": asyncio.get_event_loop().time() * 1000
        })

        # --- monitoring: update only when real tickers are involved ---
        metrics.gauge("websocket.active_connections", self._market_client_count())

        logger.info(f"Client {client_id} subscribed to: {', '.join(ticker_list)}")

    async def handle_unsubscribe(self, client_id: str, tickers):
        """Handle unsubscription request"""
        websocket = self.active_connections.get(client_id)
        if not websocket:
            return

        ticker_list = tickers if isinstance(tickers, list) else [tickers]

        for ticker in ticker_list:
            self.subscriptions[client_id].discard(ticker.upper())

        await self.send_message(websocket, {
            "type": "unsubscribed",
            "tickers": ticker_list,
            "timestamp": asyncio.get_event_loop().time() * 1000
        })

        metrics.gauge("websocket.active_connections", self._market_client_count())

        logger.info(f"Client {client_id} unsubscribed from: {', '.join(ticker_list)}")

    async def broadcast_tick(self, tick: dict):
        """Broadcast tick to subscribed clients"""
        ticker = tick.get("ticker")
        if not ticker:
            return

        # Update cache
        self.tick_cache[ticker] = tick

        # Broadcast to subscribed clients
        sent_count = 0
        disconnected_clients = []

        for client_id, websocket in self.active_connections.items():
            if ticker in self.subscriptions.get(client_id, set()):
                try:
                    await self.send_message(websocket, {
                        "type": "tick",
                        "data": tick
                    })
                    sent_count += 1
                except Exception as e:
                    logger.error(f"Error broadcasting to client {client_id}: {e}")
                    disconnected_clients.append(client_id)

        # --- monitoring ---
        if sent_count > 0:
            metrics.counter("websocket.broadcasts", sent_count)

        # Clean up disconnected clients
        for client_id in disconnected_clients:
            self.disconnect(client_id)

    # ------------------------------------------------------------------
    # Live metrics push (pseudo-ticker __METRICS__)
    # ------------------------------------------------------------------

    async def _push_metrics_snapshot(self):
        """Push a metric snapshot to every client subscribed to __METRICS__."""
        from ..monitoring.collector import metrics as _m
        from ..monitoring.alerts import get_alerts

        snapshot = _m.snapshot(window=60.0)
        snapshot["alerts"] = get_alerts(limit=10)

        payload = {
            "type": "metrics",
            "data": snapshot,
        }

        disconnected = []
        for client_id, websocket in self.active_connections.items():
            if "__METRICS__" in self.subscriptions.get(client_id, set()):
                try:
                    await self.send_message(websocket, payload)
                except Exception:
                    disconnected.append(client_id)

        for client_id in disconnected:
            self.disconnect(client_id)

    async def _metrics_push_loop(self):
        """Push metric snapshots every second to __METRICS__ subscribers."""
        while self.is_running:
            await asyncio.sleep(1)
            if not self.is_running:
                break
            try:
                await self._push_metrics_snapshot()
            except Exception as e:
                logger.error(f"Error pushing metrics snapshot: {e}")

    async def start_kafka_consumer(self):
        """Start Kafka consumer for market ticks"""
        try:
            self.kafka_consumer = AIOKafkaConsumer(
                settings.KAFKA_TOPIC_TICKS,
                bootstrap_servers=settings.KAFKA_BROKERS,
                group_id="websocket-group",
                value_deserializer=lambda m: json.loads(m.decode('utf-8'))
            )

            await self.kafka_consumer.start()
            logger.info("WebSocket Kafka consumer connected")

            self.is_running = True

            # Start the metrics push loop alongside the Kafka consumer
            metrics_task = asyncio.create_task(self._metrics_push_loop())

            # Consume messages
            try:
                async for message in self.kafka_consumer:
                    if not self.is_running:
                        break

                    tick = message.value
                    await self.broadcast_tick(tick)
            finally:
                metrics_task.cancel()

        except Exception as e:
            logger.error(f"Error in Kafka consumer: {e}")
        finally:
            if self.kafka_consumer:
                await self.kafka_consumer.stop()

    async def shutdown(self):
        """Shutdown WebSocket manager"""
        logger.info("Shutting down WebSocket manager")
        self.is_running = False

        # Close all client connections
        for client_id in list(self.active_connections.keys()):
            try:
                await self.active_connections[client_id].close()
            except Exception as e:
                logger.error(f"Error closing connection for {client_id}: {e}")

        # Stop Kafka consumer
        if self.kafka_consumer:
            await self.kafka_consumer.stop()

        logger.info("WebSocket manager shutdown complete")


# Global WebSocket manager instance
ws_manager = WebSocketManager()


async def websocket_endpoint(websocket: WebSocket, client_id: str):
    """WebSocket endpoint handler"""
    await ws_manager.connect(websocket, client_id)

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            await ws_manager.handle_message(client_id, message)
    except WebSocketDisconnect:
        ws_manager.disconnect(client_id)
    except Exception as e:
        logger.error(f"WebSocket error for client {client_id}: {e}")
        ws_manager.disconnect(client_id)
