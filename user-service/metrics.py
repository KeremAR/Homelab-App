"""Prometheus metrics with OpenMetrics exemplar support for user-service."""

from prometheus_client import Counter, Histogram, REGISTRY
from prometheus_client.openmetrics.exposition import (
    CONTENT_TYPE_LATEST,
    generate_latest,
)
from starlette.requests import Request
from starlette.responses import Response

from opentelemetry import trace
from opentelemetry.trace import TraceFlags


PROBE_PATHS = frozenset({"/health", "/ready", "/metrics"})
LATENCY_BUCKETS = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.075,
    0.1,
    0.25,
    0.5,
    0.75,
    1.0,
    2.5,
    5.0,
    7.5,
    10.0,
)

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total number of HTTP requests by method, status and handler.",
    labelnames=("method", "status", "handler"),
)
REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration by method, status and handler.",
    labelnames=("method", "status", "handler"),
    buckets=LATENCY_BUCKETS,
)


def normalized_route(request: Request) -> str:
    """Return a route template, never an unbounded raw request path."""
    route = request.scope.get("route")
    route_path = getattr(route, "path", None)
    if isinstance(route_path, str) and route_path.startswith("/"):
        return route_path
    return "unmatched"


def status_label(status_code: int) -> str:
    """Return the bounded HTTP status code label used by existing dashboards."""
    return str(status_code)


def _sampled_trace_exemplar() -> dict[str, str] | None:
    span_context = trace.get_current_span().get_span_context()
    if (
        not span_context.is_valid
        or (span_context.trace_flags & TraceFlags.SAMPLED) == 0
    ):
        return None
    return {"trace_id": f"{span_context.trace_id:032x}"}


def observe_request(
    request: Request, status_code: int, duration_seconds: float
) -> None:
    """Record a request and attach an exemplar to non-probe latency samples."""
    labels = {
        "method": request.method,
        "status": status_label(status_code),
        "handler": normalized_route(request),
    }
    REQUEST_COUNT.labels(**labels).inc()

    if request.url.path in PROBE_PATHS:
        return

    REQUEST_DURATION.labels(**labels).observe(
        max(duration_seconds, 0.0),
        exemplar=_sampled_trace_exemplar(),
    )


def openmetrics_response() -> Response:
    """Render the process registry using the OpenMetrics exposition format."""
    return Response(
        content=generate_latest(REGISTRY),
        headers={"Content-Type": CONTENT_TYPE_LATEST},
    )
