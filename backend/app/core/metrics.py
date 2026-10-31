"""Lightweight in-process metrics — Prometheus text exposition, zero deps.

Scope (honest): single-process counters suitable for the Termux/small-server
deployment target. Not a distributed metrics backend. Exposed at
``GET /api/v1/metrics`` (disable with ``METRICS_ENABLED=false``).

Counter model:
    counters[f"{name}{labels}"] = float total
    names are declared so ``render()`` emits ``# TYPE`` hints in order.
"""

from __future__ import annotations

import threading
from collections import defaultdict


class MetricsRegistry:
    """Thread-safe counter registry with Prometheus text rendering."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._values: dict[str, float] = defaultdict(float)
        self._types: dict[str, str] = {}  # metric name -> TYPE comment

    def declare(self, name: str, mtype: str = "counter", help: str = "") -> None:
        with self._lock:
            self._types[name] = mtype
            if help:
                self._types[f"__help__{name}"] = help

    def inc(self, name: str, labels: dict[str, str] | None = None, amount: float = 1.0) -> None:
        label_str = _render_labels(labels)
        key = f"{name}{label_str}"
        with self._lock:
            self._values[key] += amount

    def render(self) -> str:
        """Render in Prometheus text format (sorted for stable output)."""
        with self._lock:
            emitted_types: set[str] = set()
            lines: list[str] = []
            for key in sorted(self._values):
                name = key.split("{", 1)[0]
                if name in self._types and name not in emitted_types:
                    help_text = self._types.get(f"__help__{name}", "")
                    if help_text:
                        lines.append(f"# HELP {name} {help_text}")
                    lines.append(f"# TYPE {name} {self._types[name]}")
                    emitted_types.add(name)
                value = self._values[key]
                value_str = str(int(value)) if float(value).is_integer() else f"{value:.6f}"
                lines.append(f"{key} {value_str}")
            return ("\n".join(lines) + "\n") if lines else ""


def _render_labels(labels: dict[str, str] | None) -> str:
    if not labels:
        return ""
    inner = ",".join(f'{k}="{_escape_label(v)}"' for k, v in sorted(labels.items()))
    return "{" + inner + "}"


def _escape_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


# --- Process-wide registry ---------------------------------------------------

REGISTRY = MetricsRegistry()

# Declare every metric the app emits (single place, easy to audit).
REGISTRY.declare(
    "tayf_http_requests_total",
    help="HTTP requests handled, by method and status code.",
)
REGISTRY.declare(
    "tayf_jobs_total",
    help="Generation jobs reaching a terminal state, by status.",
)
REGISTRY.declare(
    "tayf_credits_total",
    help="Credit ledger movements, by kind (granted|charged|refunded).",
)


def record_http_request(method: str, status_code: int) -> None:
    REGISTRY.inc("tayf_http_requests_total", {"method": method, "status": str(status_code)})


def record_job_terminal(status_value: str) -> None:
    REGISTRY.inc("tayf_jobs_total", {"status": status_value})


def record_credits(kind: str, amount: int) -> None:
    REGISTRY.inc("tayf_credits_total", {"kind": kind}, amount=float(amount))
