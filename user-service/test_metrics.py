from types import SimpleNamespace

from fastapi.testclient import TestClient
from opentelemetry import context, trace
from starlette.requests import Request

from app import app
from metrics import REQUEST_DURATION, observe_request


def make_request(path: str, route_path: str | None = None, method: str = "GET"):
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "scheme": "http",
        "root_path": "",
    }
    if route_path is not None:
        scope["route"] = SimpleNamespace(path=route_path)
    return Request(scope)


def duration_samples(handler: str, method: str = "GET"):
    family = next(
        family
        for family in REQUEST_DURATION.collect()
        if family.name == "http_request_duration_seconds"
    )
    return [
        sample
        for sample in family.samples
        if sample.labels["handler"] == handler and sample.labels["method"] == method
    ]


def test_sampled_span_is_added_as_a_trace_id_exemplar():
    request = make_request(
        "/__metrics_test__/sampled/42",
        "/__metrics_test__/sampled/{todo_id}",
    )
    span = trace.NonRecordingSpan(
        trace.SpanContext(
            trace_id=0x1234567890ABCDEF1234567890ABCDEF,
            span_id=0x1234567890ABCDEF,
            is_remote=False,
            trace_flags=trace.TraceFlags(trace.TraceFlags.SAMPLED),
        )
    )
    token = context.attach(trace.set_span_in_context(span))
    try:
        observe_request(request, 200, 0.1)
    finally:
        context.detach(token)

    exemplars = [
        sample.exemplar
        for sample in duration_samples("/__metrics_test__/sampled/{todo_id}")
        if sample.exemplar is not None
    ]
    assert len(exemplars) == 1
    assert exemplars[0].labels == {"trace_id": "1234567890abcdef1234567890abcdef"}


def test_invalid_or_unsampled_span_records_latency_without_exemplar():
    observe_request(
        make_request("/api/v1/no-span", "/api/v1/no-span"),
        200,
        0.1,
    )

    unsampled = trace.NonRecordingSpan(
        trace.SpanContext(
            trace_id=0x2234567890ABCDEF1234567890ABCDEF,
            span_id=0x2234567890ABCDEF,
            is_remote=False,
            trace_flags=trace.TraceFlags(0),
        )
    )
    token = context.attach(trace.set_span_in_context(unsampled))
    try:
        observe_request(
            make_request("/api/v1/unsampled", "/api/v1/unsampled", method="POST"),
            201,
            0.1,
        )
    finally:
        context.detach(token)

    assert all(
        sample.exemplar is None for sample in duration_samples("/api/v1/no-span")
    )
    assert all(
        sample.exemplar is None
        for sample in duration_samples("/api/v1/unsampled", method="POST")
    )


def test_metric_labels_use_normalized_routes_and_no_request_ids():
    observe_request(
        make_request("/api/v1/todos/987", "/api/v1/todos/{todo_id}"),
        200,
        0.1,
    )

    samples = duration_samples("/api/v1/todos/{todo_id}")
    assert samples
    assert all("987" not in sample.labels.values() for sample in samples)
    assert all(
        set(sample.labels) == {"handler", "method", "status", "le"}
        for sample in samples
        if sample.name.endswith("_bucket")
    )


def test_probe_paths_do_not_enter_latency_histogram():
    for path in ("/health", "/ready", "/metrics"):
        observe_request(make_request(path, path), 200, 0.1)
        assert not duration_samples(path)


def test_metrics_endpoint_uses_openmetrics_and_is_declared_once():
    client = TestClient(app)
    response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/openmetrics-text")
    assert "# EOF" in response.text
    assert sum(route.path == "/metrics" for route in app.routes) == 1
