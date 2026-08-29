"""JSON stdout logging with OpenTelemetry trace correlation for user-service."""

import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

from opentelemetry import trace
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.trace import TraceFlags
from pythonjsonlogger import json as jsonlogger


_CONFIGURED = False
_SENSITIVE_TEXT = re.compile(
    r"(?i)(?:authorization|password|passwd|secret|token)(?:\s*[:=]\s*)[^\s,;]+"
)
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")


def _redact(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    value = _SENSITIVE_TEXT.sub("[REDACTED]", value)
    return _EMAIL.sub("[REDACTED]", value)


def _resource_attributes() -> dict[str, str]:
    attributes: dict[str, str] = {}
    for item in os.getenv("OTEL_RESOURCE_ATTRIBUTES", "").split(","):
        key, separator, value = item.partition("=")
        if separator and key.strip() and value.strip():
            attributes[key.strip()] = value.strip()
    return attributes


def otel_resource_attributes(service_name: str) -> dict[str, str]:
    """Return explicit resource attributes while honoring OTEL env settings."""
    attributes = _resource_attributes()
    attributes.setdefault("service.name", service_name)
    attributes.setdefault("service.namespace", "homelab-app")
    attributes.setdefault("service.version", os.getenv("SERVICE_VERSION", "dev"))
    attributes.setdefault(
        "deployment.environment.name",
        os.getenv("DEPLOYMENT_ENVIRONMENT", "development"),
    )
    attributes.setdefault("k8s.cluster.name", os.getenv("K8S_CLUSTER_NAME", "homelab"))
    return attributes


class JsonLogFormatter(jsonlogger.JsonFormatter):
    """Emit a compact, allow-listed JSON record for stdout collection."""

    _EXTRA_FIELDS = (
        "service_name",
        "service_namespace",
        "service_version",
        "deployment_environment",
        "event_name",
        "actor_id",
        "resource_type",
        "resource_id",
        "outcome",
        "http_method",
        "http_route",
        "http_status_code",
        "duration_ms",
        "trace_id",
        "span_id",
        "trace_sampled",
        "changed_fields",
    )

    def __init__(self, service_name: str) -> None:
        super().__init__(fmt="%(message)s")
        self._service_name = service_name

    def add_fields(
        self,
        log_record: dict[str, Any],
        record: logging.LogRecord,
        message_dict: dict[str, Any],
    ) -> None:
        super().add_fields(log_record, record, message_dict)

        attributes = otel_resource_attributes(self._service_name)
        span_context = trace.get_current_span().get_span_context()
        trace_id = None
        span_id = None
        trace_sampled = None
        if span_context.is_valid:
            trace_id = f"{span_context.trace_id:032x}"
            span_id = f"{span_context.span_id:016x}"
            trace_sampled = bool(span_context.trace_flags & TraceFlags.SAMPLED)

        fields: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "severity": record.levelname,
            "logger": record.name,
            "message": _redact(record.getMessage()),
            "service_name": attributes.get("service.name", self._service_name),
            "service_namespace": attributes.get("service.namespace"),
            "service_version": attributes.get("service.version"),
            "deployment_environment": attributes.get("deployment.environment.name"),
            "trace_id": trace_id,
            "span_id": span_id,
            "trace_sampled": trace_sampled,
        }

        for field in self._EXTRA_FIELDS:
            if hasattr(record, field):
                fields[field] = _redact(getattr(record, field))

        if record.exc_info:
            fields["exception_type"] = record.exc_info[0].__name__
            fields["exception_message"] = _redact(str(record.exc_info[1]))
            fields["exception"] = _redact(self.formatException(record.exc_info))

        log_record.clear()
        log_record.update(fields)


def configure_logging(service_name: str) -> None:
    """Configure one JSON stream handler for app and Uvicorn loggers."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    # Add OTEL trace/span fields to LogRecords without exporting application logs.
    LoggingInstrumentor().instrument(
        set_logging_format=False,
        inject_trace_context=True,
    )

    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter(service_name))

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)

    for logger_name in ("app", "uvicorn", "uvicorn.error"):
        service_logger = logging.getLogger(logger_name)
        service_logger.handlers.clear()
        service_logger.propagate = True
        service_logger.setLevel(level)

    access_logger = logging.getLogger("uvicorn.access")
    access_logger.handlers.clear()
    access_logger.disabled = True
    access_logger.propagate = False
    _CONFIGURED = True
