import json
import logging
from io import StringIO

from logging_config import JsonLogFormatter
from opentelemetry import context, trace


def capture_record(message, **fields):
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonLogFormatter("todo-service"))
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
        http_route="/api/v1/todos",
        http_status_code=200,
        duration_ms=8.5,
    )

    assert record["severity"] == "INFO"
    assert record["logger"] == "logging-test"
    assert record["message"] == "HTTP request completed"
    assert record["service_name"] == "todo-service"
    assert record["event_name"] == "http.request.completed"
    assert record["http_method"] == "GET"
    assert record["http_route"] == "/api/v1/todos"
    assert record["http_status_code"] == 200
    assert record["duration_ms"] == 8.5
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
        "Audit event: todo.updated",
        event_name="todo.updated",
        actor_id=3,
        resource_type="todo",
        resource_id=12,
        outcome="success",
        changed_fields=["completed", "title"],
    )

    assert record["event_name"] == "todo.updated"
    assert record["actor_id"] == 3
    assert record["resource_type"] == "todo"
    assert record["resource_id"] == 12
    assert record["outcome"] == "success"
    assert record["changed_fields"] == ["completed", "title"]


def test_todo_audit_events_use_ids_and_distinguish_mutations():
    events = [
        ("todo.created", 12),
        ("todo.updated", 12),
        ("todo.deleted", 12),
    ]
    records = [
        capture_record(
            f"Audit event: {event_name}",
            event_name=event_name,
            actor_id=3,
            resource_type="todo",
            resource_id=resource_id,
            outcome="success",
            changed_fields=["completed"] if event_name == "todo.updated" else None,
        )
        for event_name, resource_id in events
    ]

    assert [record["event_name"] for record in records] == [
        "todo.created",
        "todo.updated",
        "todo.deleted",
    ]
    assert all(record["actor_id"] == 3 for record in records)
    assert all(record["resource_id"] == 12 for record in records)
    assert records[1]["changed_fields"] == ["completed"]
    assert "private todo title" not in json.dumps(records)
    assert "private todo description" not in json.dumps(records)


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
