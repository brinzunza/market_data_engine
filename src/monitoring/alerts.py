"""
Alert Engine — threshold-based alerting over live metrics.

How it works
------------
1.  A set of *rules* is defined.  Each rule names a metric, a comparison
    operator, a threshold value, and a severity (warning / critical).
2.  An async loop (started by main.py's lifespan) calls `check()` every
    CHECK_INTERVAL seconds.
3.  Any rule that fires is appended to a bounded ring-buffer of recent
    alerts.  Duplicate alerts (same rule, within COOLDOWN seconds) are
    suppressed so you don't get flooded.
4.  `get_alerts()` returns the ring-buffer contents — consumed by the
    REST endpoint and the WebSocket metrics push.

Adding a rule
-------------
Just append to ALERT_RULES:

    {"metric": "processor.flush_latency_ms", "stat": "p99",
     "op": ">", "threshold": 200, "severity": "critical",
     "message": "DB flush p99 latency exceeded 200 ms"}

The ``stat`` field tells the engine *which* number to compare:
  - For histograms: min | max | mean | p50 | p95 | p99
  - For counters:   rate_per_sec | total | in_window
  - For gauges:     value
"""

import time
import asyncio
import logging
from collections import deque
from typing import Any, Dict, List

from .collector import metrics

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# How often the alert loop runs (seconds).
CHECK_INTERVAL = 5

# How long (seconds) before the same rule can fire again.
COOLDOWN = 60

# How many alert entries we keep in memory.
MAX_ALERT_HISTORY = 200

# ---------------------------------------------------------------------------
# Rule definitions
# ---------------------------------------------------------------------------
# Each rule is evaluated every CHECK_INTERVAL seconds.
# ``stat`` picks which derived number to compare.

ALERT_RULES: List[Dict[str, Any]] = [
    # --- Generator ---
    {
        "metric":    "generator.ticks_produced",
        "kind":      "counter",
        "stat":      "rate_per_sec",
        "op":        "<",
        "threshold": 1,          # less than 1 tick/sec means generator stalled
        "severity":  "critical",
        "message":   "Generator tick rate dropped below 1/sec — generator may be stalled",
    },
    {
        "metric":    "generator.produce_latency_ms",
        "kind":      "histogram",
        "stat":      "p99",
        "op":        ">",
        "threshold": 500,
        "severity":  "warning",
        "message":   "Kafka produce p99 latency exceeded 500 ms",
    },
    # --- Processor ---
    {
        "metric":    "processor.flush_latency_ms",
        "kind":      "histogram",
        "stat":      "p99",
        "op":        ">",
        "threshold": 200,
        "severity":  "critical",
        "message":   "DB flush p99 latency exceeded 200 ms",
    },
    {
        "metric":    "processor.buffer_depth",
        "kind":      "gauge",
        "stat":      "value",
        "op":        ">",
        "threshold": 500,
        "severity":  "warning",
        "message":   "Processor buffer depth exceeded 500 — backpressure building",
    },
    {
        "metric":    "processor.ticks_consumed",
        "kind":      "counter",
        "stat":      "rate_per_sec",
        "op":        "<",
        "threshold": 1,
        "severity":  "critical",
        "message":   "Processor tick consumption rate dropped below 1/sec — consumer may be stalled",
    },
    # --- API ---
    {
        "metric":    "api.errors",
        "kind":      "counter",
        "stat":      "rate_per_sec",
        "op":        ">",
        "threshold": 5,
        "severity":  "warning",
        "message":   "API error rate exceeded 5 errors/sec",
    },
    {
        "metric":    "api.request_latency_ms",
        "kind":      "histogram",
        "stat":      "p99",
        "op":        ">",
        "threshold": 1000,
        "severity":  "warning",
        "message":   "API request p99 latency exceeded 1000 ms",
    },
    # --- WebSocket ---
    {
        "metric":    "websocket.active_connections",
        "kind":      "gauge",
        "stat":      "value",
        "op":        ">",
        "threshold": 100,
        "severity":  "warning",
        "message":   "WebSocket active connections exceeded 100",
    },
]

# ---------------------------------------------------------------------------
# Alert engine
# ---------------------------------------------------------------------------

# Ring-buffer of fired alerts, newest first on read.
_alert_history: deque = deque(maxlen=MAX_ALERT_HISTORY)

# last-fired timestamp per rule index — used for cooldown.
_last_fired: Dict[int, float] = {}

_OPERATORS = {
    ">":  lambda a, b: a > b,
    "<":  lambda a, b: a < b,
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
    "==": lambda a, b: a == b,
}


def _read_metric_value(rule: Dict[str, Any]) -> float:
    """Pull the single comparable number out of the collector for this rule."""
    name   = rule["metric"]
    kind   = rule["kind"]
    stat   = rule["stat"]

    if kind == "counter":
        if stat == "rate_per_sec":
            return metrics.get_counter_rate(name)
        elif stat == "total":
            return float(metrics.get_counter(name))
        else:  # in_window
            snap = metrics.snapshot()
            entry = snap["counters"].get(name, {})
            return float(entry.get("in_window", 0))

    elif kind == "gauge":
        return metrics.get_gauge(name)

    elif kind == "histogram":
        stats = metrics.get_histogram_stats(name)
        return stats.get(stat, 0.0)

    return 0.0


def check() -> List[Dict[str, Any]]:
    """
    Evaluate every rule.  Append any new alerts to history.
    Returns the list of alerts that fired *this* call (useful for push).
    """
    now = time.time()
    fired_now: List[Dict[str, Any]] = []

    for idx, rule in enumerate(ALERT_RULES):
        # Cooldown: skip if this rule fired recently.
        if now - _last_fired.get(idx, 0) < COOLDOWN:
            continue

        value = _read_metric_value(rule)
        op_fn = _OPERATORS.get(rule["op"])
        if op_fn is None:
            continue

        if op_fn(value, rule["threshold"]):
            alert = {
                "id":        idx,
                "severity":  rule["severity"],
                "metric":    rule["metric"],
                "stat":      rule["stat"],
                "operator":  rule["op"],
                "threshold": rule["threshold"],
                "actual":    round(value, 4),
                "message":   rule["message"],
                "fired_at":  now,
            }
            _alert_history.appendleft(alert)
            _last_fired[idx] = now
            fired_now.append(alert)
            logger.warning(
                f"[ALERT][{rule['severity'].upper()}] {rule['message']} "
                f"(actual={value:.4f})"
            )

    return fired_now


def get_alerts(limit: int = 50) -> List[Dict[str, Any]]:
    """Return the most recent alerts (newest first)."""
    return list(_alert_history)[:limit]


def clear_alerts() -> None:
    """Wipe alert history (e.g. for testing)."""
    _alert_history.clear()


# ---------------------------------------------------------------------------
# Async loop — started by main.py lifespan
# ---------------------------------------------------------------------------

async def alert_loop():
    """Run forever, checking alerts every CHECK_INTERVAL seconds."""
    logger.info(f"Alert loop started (check every {CHECK_INTERVAL}s)")
    while True:
        try:
            check()
        except Exception as e:
            logger.error(f"Error in alert check: {e}")
        await asyncio.sleep(CHECK_INTERVAL)
