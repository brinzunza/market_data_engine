"""
Metric Collector — thread-safe, in-process metric store.

Design goals:
- Zero external dependencies (stdlib only).
- Thread-safe: safe to call from asyncio tasks and sync code alike.
- Time-windowed: every snapshot covers the last N seconds so percentile
  and rate calculations stay meaningful regardless of when you ask.
- Singleton: imported once, shared across the whole process.

Metric kinds
------------
counter   – monotonically increasing (requests, ticks produced, errors)
gauge     – point-in-time value (active WS connections, buffer depth)
histogram – raw latency samples; percentiles computed on read

Usage
-----
    from src.monitoring.collector import metrics

    metrics.counter("generator.ticks_produced")
    metrics.histogram("processor.flush_latency_ms", 42.7)
    metrics.gauge("websocket.active_connections", 12)

    snapshot = metrics.snapshot()   # dict ready to JSON-serialise
"""

import time
import threading
from collections import deque
from typing import Any, Dict, List


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _percentile(sorted_vals: List[float], p: float) -> float:
    """Compute the p-th percentile (0-100) from an already-sorted list."""
    if not sorted_vals:
        return 0.0
    idx = (p / 100.0) * (len(sorted_vals) - 1)
    lower = int(idx)
    upper = lower + 1
    if upper >= len(sorted_vals):
        return sorted_vals[-1]
    frac = idx - lower
    return sorted_vals[lower] * (1 - frac) + sorted_vals[upper] * frac


# ---------------------------------------------------------------------------
# Core collector
# ---------------------------------------------------------------------------

class MetricCollector:
    """
    Thread-safe collector that supports counters, gauges and histograms.

    All time-windowed queries default to the last 60 seconds so that
    short-lived spikes (e.g. a latency burst) are visible without
    requiring the caller to track timestamps manually.
    """

    # How many seconds of histogram samples we retain.
    WINDOW_SECONDS = 60
    # Max samples kept per histogram (ring-buffer style).
    MAX_SAMPLES = 5000

    def __init__(self):
        self._lock = threading.Lock()

        # counters: name -> int  (total lifetime count)
        self._counters: Dict[str, int] = {}
        # counters with timestamps for rate calculations: name -> deque of (ts, 1)
        self._counter_events: Dict[str, deque] = {}

        # gauges: name -> (value, timestamp)
        self._gauges: Dict[str, tuple] = {}

        # histograms: name -> deque of (timestamp, value)
        self._histograms: Dict[str, deque] = {}

        # Track when the collector was created (uptime reference)
        self._started_at = time.time()

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def counter(self, name: str, increment: int = 1) -> None:
        """Increment a named counter."""
        now = time.time()
        with self._lock:
            self._counters[name] = self._counters.get(name, 0) + increment
            if name not in self._counter_events:
                self._counter_events[name] = deque()
            self._counter_events[name].append(now)
            # Trim old events outside the window
            cutoff = now - self.WINDOW_SECONDS
            while self._counter_events[name] and self._counter_events[name][0] < cutoff:
                self._counter_events[name].popleft()

    def gauge(self, name: str, value: float) -> None:
        """Set a gauge to an absolute value."""
        with self._lock:
            self._gauges[name] = (value, time.time())

    def histogram(self, name: str, value: float) -> None:
        """Record a single sample into a histogram (e.g. latency in ms)."""
        now = time.time()
        with self._lock:
            if name not in self._histograms:
                self._histograms[name] = deque(maxlen=self.MAX_SAMPLES)
            self._histograms[name].append((now, value))
            # Trim samples older than the window
            cutoff = now - self.WINDOW_SECONDS
            while self._histograms[name] and self._histograms[name][0][0] < cutoff:
                self._histograms[name].popleft()

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------

    def get_counter(self, name: str) -> int:
        with self._lock:
            return self._counters.get(name, 0)

    def get_counter_rate(self, name: str, window: float = 60.0) -> float:
        """Events per second over the given window."""
        now = time.time()
        cutoff = now - window
        with self._lock:
            events = self._counter_events.get(name, deque())
            count = sum(1 for ts in events if ts >= cutoff)
        return count / window if window > 0 else 0.0

    def get_gauge(self, name: str) -> float:
        with self._lock:
            entry = self._gauges.get(name)
            return entry[0] if entry else 0.0

    def get_histogram_stats(self, name: str, window: float = 60.0) -> Dict[str, Any]:
        """Return min/max/mean/p50/p95/p99/count for samples in the window."""
        now = time.time()
        cutoff = now - window
        with self._lock:
            samples = [v for (ts, v) in self._histograms.get(name, deque()) if ts >= cutoff]

        if not samples:
            return {"count": 0, "min": 0, "max": 0, "mean": 0, "p50": 0, "p95": 0, "p99": 0}

        samples.sort()
        return {
            "count": len(samples),
            "min": round(samples[0], 3),
            "max": round(samples[-1], 3),
            "mean": round(sum(samples) / len(samples), 3),
            "p50": round(_percentile(samples, 50), 3),
            "p95": round(_percentile(samples, 95), 3),
            "p99": round(_percentile(samples, 99), 3),
        }

    # ------------------------------------------------------------------
    # Full snapshot (for the REST endpoint / WS push)
    # ------------------------------------------------------------------

    def snapshot(self, window: float = 60.0) -> Dict[str, Any]:
        """
        Return a JSON-serialisable dict with every metric recorded so far.
        Counters include both lifetime total and per-second rate.
        """
        now = time.time()
        result: Dict[str, Any] = {
            "timestamp": now,
            "uptime_seconds": round(now - self._started_at, 1),
            "window_seconds": window,
            "counters": {},
            "gauges": {},
            "histograms": {},
        }

        with self._lock:
            # --- counters ---
            cutoff = now - window
            for name, total in self._counters.items():
                events = self._counter_events.get(name, deque())
                in_window = sum(1 for ts in events if ts >= cutoff)
                result["counters"][name] = {
                    "total": total,
                    "in_window": in_window,
                    "rate_per_sec": round(in_window / window, 2) if window > 0 else 0,
                }

            # --- gauges ---
            for name, (value, ts) in self._gauges.items():
                result["gauges"][name] = {
                    "value": value,
                    "updated_at": ts,
                }

            # --- histograms (computed outside the lock to keep critical
            #     section short, but we grab a snapshot of the deque here) ---
            hist_snapshots = {
                name: list(dq) for name, dq in self._histograms.items()
            }

        # Compute percentiles outside the lock
        for name, samples_raw in hist_snapshots.items():
            samples = [v for (ts, v) in samples_raw if ts >= (now - window)]
            if not samples:
                result["histograms"][name] = {"count": 0, "min": 0, "max": 0, "mean": 0, "p50": 0, "p95": 0, "p99": 0}
                continue
            samples.sort()
            result["histograms"][name] = {
                "count": len(samples),
                "min": round(samples[0], 3),
                "max": round(samples[-1], 3),
                "mean": round(sum(samples) / len(samples), 3),
                "p50": round(_percentile(samples, 50), 3),
                "p95": round(_percentile(samples, 95), 3),
                "p99": round(_percentile(samples, 99), 3),
            }

        return result


# ---------------------------------------------------------------------------
# Global singleton — import this everywhere
# ---------------------------------------------------------------------------
metrics = MetricCollector()
