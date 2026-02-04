"""
Monitoring REST endpoints.

All endpoints are intentionally public (no API-key gate) so that
health-check dashboards and uptime monitors can hit them without
credentials.  If you want to lock them down later just add the
/api/v1/monitor prefix to the public_paths exclusion list in
APIKeyMiddleware.

Endpoints
---------
GET /api/v1/monitor/stats          Full metric snapshot (counters, gauges, histograms)
GET /api/v1/monitor/alerts         Recent alert history
GET /api/v1/monitor/health         Rich health report (subsystem status)
"""

import time
import logging
from fastapi import APIRouter, Query

from ..monitoring.collector import metrics
from ..monitoring.alerts import get_alerts

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/monitor", tags=["monitoring"])


# ---------------------------------------------------------------------------
# /stats  — full metric snapshot
# ---------------------------------------------------------------------------

@router.get("/stats")
async def get_stats(window: int = Query(default=60, ge=1, le=3600)):
    """
    Return a snapshot of all recorded metrics over the last *window* seconds.

    Query params:
        window  – number of seconds to look back (default 60, max 3600)
    """
    return {
        "success": True,
        "data": metrics.snapshot(window=float(window)),
    }


# ---------------------------------------------------------------------------
# /alerts  — recent alert history
# ---------------------------------------------------------------------------

@router.get("/alerts")
async def get_alerts_endpoint(limit: int = Query(default=50, ge=1, le=500)):
    """
    Return the most recent alerts, newest first.

    Query params:
        limit   – how many alerts to return (default 50)
    """
    alerts = get_alerts(limit=limit)
    return {
        "success": True,
        "data": {
            "count": len(alerts),
            "alerts": alerts,
        },
    }


# ---------------------------------------------------------------------------
# /health  — rich health report
# ---------------------------------------------------------------------------

@router.get("/health")
async def get_health():
    """
    Richer health check than GET /.  Reports on each subsystem based on
    the live metrics.  A subsystem is 'healthy' if its key rate/latency
    metrics are within normal bounds.
    """
    now = time.time()
    snap = metrics.snapshot(window=60.0)

    # --- Generator health ---
    gen_rate = snap["counters"].get("generator.ticks_produced", {}).get("rate_per_sec", 0)
    gen_latency = snap["histograms"].get("generator.produce_latency_ms", {})
    gen_healthy = gen_rate > 0  # at least some ticks in the last 60 s

    # --- Processor health ---
    proc_rate = snap["counters"].get("processor.ticks_consumed", {}).get("rate_per_sec", 0)
    proc_latency = snap["histograms"].get("processor.flush_latency_ms", {})
    proc_buffer = snap["gauges"].get("processor.buffer_depth", {}).get("value", 0)
    proc_healthy = proc_rate > 0

    # --- API health ---
    api_requests = snap["counters"].get("api.requests", {}).get("rate_per_sec", 0)
    api_errors = snap["counters"].get("api.errors", {}).get("rate_per_sec", 0)
    api_latency = snap["histograms"].get("api.request_latency_ms", {})
    api_healthy = True  # API is healthy if we're responding (we are)

    # --- WebSocket health ---
    ws_connections = snap["gauges"].get("websocket.active_connections", {}).get("value", 0)
    ws_broadcasts = snap["counters"].get("websocket.broadcasts", {}).get("rate_per_sec", 0)

    # --- Recent alerts ---
    recent_alerts = get_alerts(limit=5)
    has_critical = any(a["severity"] == "critical" for a in recent_alerts)

    # Overall status
    all_healthy = gen_healthy and proc_healthy and api_healthy and not has_critical
    overall_status = "healthy" if all_healthy else ("degraded" if not has_critical else "critical")

    return {
        "success": True,
        "data": {
            "status": overall_status,
            "timestamp": now,
            "uptime_seconds": snap.get("uptime_seconds", 0),
            "subsystems": {
                "generator": {
                    "status": "healthy" if gen_healthy else "unhealthy",
                    "ticks_per_sec": gen_rate,
                    "produce_latency_ms": gen_latency,
                },
                "processor": {
                    "status": "healthy" if proc_healthy else "unhealthy",
                    "ticks_per_sec": proc_rate,
                    "flush_latency_ms": proc_latency,
                    "buffer_depth": proc_buffer,
                },
                "api": {
                    "status": "healthy" if api_healthy else "unhealthy",
                    "requests_per_sec": api_requests,
                    "errors_per_sec": api_errors,
                    "request_latency_ms": api_latency,
                },
                "websocket": {
                    "status": "healthy",
                    "active_connections": ws_connections,
                    "broadcasts_per_sec": ws_broadcasts,
                },
            },
            "recent_alerts": recent_alerts,
        },
    }
