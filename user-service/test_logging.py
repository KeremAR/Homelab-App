import json
import logging
from io import StringIO

from logging_config import JsonLogFormatter
from opentelemetry import context, trace


def capture_record(message, **fields):
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonLogFormatter("user-service"))
    logger = logging.getLogger("logging-test")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)
    try:
        logger.info(message, extra=fields)
        return json.loads(stream.getvalue())
    finally:
        logger.handlers.clear()


def test_log_output_is_json_with_canonical_fields():
    record = capture_record(
        "HTTP request completed",
        event_name="http.request.completed",
        http_method="GET",
        http_route="/api/v1/auth/me",
        http_status_code=200,
        duration_ms=12.34,
    )

    assert record["severity"] == "INFO"
    assert record["logger"] == "logging-test"
    assert record["message"] == "HTTP request completed"
    assert record["service_name"] == "user-service"
    assert record["event_name"] == "http.request.completed"
    assert record["http_method"] == "GET"
    assert record["http_route"] == "/api/v1/auth/me"
    assert record["http_status_code"] == 200
    assert record["duration_ms"] == 12.34
    assert "timestamp" in record


def test_active_span_is_correlated_without_fabricated_ids():
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
        record = capture_record("request")
    finally:
        context.detach(token)

    assert record["trace_id"] == "1234567890abcdef1234567890abcdef"
    assert record["span_id"] == "1234567890abcdef"
    assert record["trace_sampled"] is True


def test_audit_fields_are_preserved():
    record = capture_record(
        "Audit event: user.registered",
        event_name="user.registered",
        actor_id=7,
        resource_type="user",
        resource_id=7,
        outcome="success",
    )

    assert record["event_name"] == "user.registered"
    assert record["actor_id"] == 7
    assert record["resource_type"] == "user"
    assert record["resource_id"] == 7
    assert record["outcome"] == "success"


def test_login_audit_outcomes_are_distinct_without_username():
    success = capture_record(
        "Audit event: auth.login_succeeded",
        event_name="auth.login_succeeded",
        actor_id=7,
        resource_type="user",
        resource_id=7,
        outcome="success",
    )
    failure = capture_record(
        "Audit event: auth.login_failed",
        event_name="auth.login_failed",
        resource_type="auth",
        outcome="failure",
    )

    assert success["event_name"] != failure["event_name"]
    assert success["outcome"] == "success"
    assert failure["outcome"] == "failure"
    assert "submitted-user" not in json.dumps([success, failure])


def test_sensitive_values_are_not_written():
    record = capture_record(
        "login password=super-secret token=jwt-value email=user@example.com",
        email="user@example.com",
        password="super-secret",
        token="jwt-value",
        authorization="Bearer jwt-value",
        title="private todo title",
        description="private todo description",
    )
    serialized = json.dumps(record)

    assert "super-secret" not in serialized
    assert "jwt-value" not in serialized
    assert "user@example.com" not in serialized
