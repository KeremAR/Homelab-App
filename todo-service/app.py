import json
import logging
import os
from pathlib import Path
from time import perf_counter
from threading import Lock
from typing import List, Optional

import jwt
import psycopg

# httpx removed - not used
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from logging_config import configure_logging, otel_resource_attributes

# OpenTelemetry SDK and Instrumentation
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_fastapi_instrumentator import Instrumentator, metrics
from psycopg.rows import dict_row
from pydantic import (
    BaseModel,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "todo-service")
configure_logging(SERVICE_NAME)
logger = logging.getLogger(__name__)

# Configure OpenTelemetry SDK
resource = Resource.create(otel_resource_attributes(SERVICE_NAME))
trace.set_tracer_provider(TracerProvider(resource=resource))
otlp_exporter = OTLPSpanExporter()
span_processor = BatchSpanProcessor(otlp_exporter)
trace.get_tracer_provider().add_span_processor(span_processor)


# Enable Psycopg instrumentation before any database connections.
PsycopgInstrumentor().instrument()

app = FastAPI(title="Todo Service", version="1.0.0")


def _request_route(request: Request) -> str:
    route = request.scope.get("route")
    return getattr(route, "path", request.url.path)


def _audit_event(
    event_name: str,
    outcome: str,
    *,
    actor_id: int | None = None,
    resource_type: str | None = None,
    resource_id: int | None = None,
    changed_fields: list[str] | None = None,
) -> None:
    fields = {
        "event_name": event_name,
        "outcome": outcome,
    }
    if actor_id is not None:
        fields["actor_id"] = actor_id
    if resource_type is not None:
        fields["resource_type"] = resource_type
    if resource_id is not None:
        fields["resource_id"] = resource_id
    if changed_fields is not None:
        fields["changed_fields"] = changed_fields
    logger.info("Audit event: %s", event_name, extra=fields)


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    started_at = perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "Unhandled request failure",
            extra={
                "event_name": "http.request.failed",
                "outcome": "failure",
                "http_method": request.method,
                "http_route": _request_route(request),
                "duration_ms": round((perf_counter() - started_at) * 1000, 2),
                "actor_id": getattr(request.state, "actor_id", None),
            },
        )
        raise

    # Health, readiness, and metrics probes are intentionally quiet on success.
    if request.url.path not in {"/health", "/ready", "/metrics"}:
        status_code = response.status_code
        level = logging.INFO if status_code < 400 else logging.WARNING
        if status_code >= 500:
            level = logging.ERROR
        logger.log(
            level,
            "HTTP request completed",
            extra={
                "event_name": "http.request.completed",
                "outcome": "success" if status_code < 400 else "failure",
                "http_method": request.method,
                "http_route": _request_route(request),
                "http_status_code": status_code,
                "duration_ms": round((perf_counter() - started_at) * 1000, 2),
                "actor_id": getattr(request.state, "actor_id", None),
            },
        )
    return response


# Enable FastAPI auto-instrumentation
FastAPIInstrumentor.instrument_app(app)

# Prometheus metrics instrumentation
Instrumentator().add(metrics.requests()).add(  # Request counter (http_requests_total)
    metrics.latency(  # Custom latency buckets
        buckets=[
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
        ]
    )
).instrument(app).expose(app)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Securityyyyy
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"
USER_SERVICE_URL = os.getenv("USER_SERVICE_URL", "http://user-service:8001")
RUNTIME_CONFIG_PATH = Path(
    os.getenv(
        "RUNTIME_CONFIG_PATH", "/etc/todo-service/runtime-config/runtime-config.json"
    )
)

# SQL Queries
SQL_GET_TODO_BY_ID_AND_USER = "SELECT * FROM todos WHERE id = %s AND user_id = %s"

# Error messages
ERROR_TODO_NOT_FOUND = "Todo not found"


class RuntimeConfig(BaseModel):
    message: str = Field(min_length=1, max_length=200)
    version: int = Field(ge=1)


_runtime_config = RuntimeConfig(
    message="Todo service is using its built-in configuration.", version=1
)
_runtime_config_lock = Lock()


def load_runtime_config() -> RuntimeConfig:
    """Validate the file first, then atomically replace the active config."""
    new_config = RuntimeConfig.model_validate_json(
        RUNTIME_CONFIG_PATH.read_text(encoding="utf-8")
    )
    global _runtime_config
    with _runtime_config_lock:
        _runtime_config = new_config
    return new_config


def get_runtime_config() -> RuntimeConfig:
    with _runtime_config_lock:
        return _runtime_config.model_copy()


class TodoCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("title must not be blank")
        return value


class TodoUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    completed: Optional[bool] = None

    @model_validator(mode="after")
    def validate_explicit_title(self):
        if "title" in self.model_fields_set:
            if self.title is None or not self.title.strip():
                raise ValueError("title must not be blank")
            self.title = self.title.strip()
        return self


class Todo(BaseModel):
    id: int
    title: str
    description: Optional[str]
    completed: bool
    user_id: int
    created_at: str


# Database setup
def get_db():  # pragma: no cover
    """Get PostgreSQL database connection"""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable is required")
    try:
        return psycopg.connect(database_url, row_factory=dict_row)
    except Exception:
        logger.exception("Database connection failed")
        raise


def init_db():  # pragma: no cover
    """Initialize database schema"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS todos (
            id SERIAL PRIMARY KEY,
            title VARCHAR(255) NOT NULL,
            description TEXT,
            completed BOOLEAN DEFAULT FALSE,
            user_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """
    )
    conn.commit()
    cursor.close()
    conn.close()


async def verify_token(request: Request, authorization: str = Header(None)):
    scheme, separator, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not separator or not token.strip():
        _audit_event("auth.token_rejected", "failure", resource_type="auth")
        raise HTTPException(status_code=401, detail="Invalid authorization header")

    try:
        payload = jwt.decode(token.strip(), SECRET_KEY, algorithms=["HS256"])
        user_id = payload.get("user_id")
        if user_id is None:
            _audit_event("auth.token_rejected", "failure", resource_type="auth")
            raise HTTPException(status_code=401, detail="Invalid token")
        request.state.actor_id = user_id
        return user_id
    except jwt.InvalidTokenError:
        _audit_event("auth.token_rejected", "failure", resource_type="auth")
        raise HTTPException(status_code=401, detail="Invalid token")


@app.on_event("startup")
async def startup_event():  # pragma: no cover
    if RUNTIME_CONFIG_PATH.is_file():
        try:
            loaded_config = load_runtime_config()
            _audit_event(
                "runtime_config.reloaded",
                "success",
                resource_type="runtime_config",
                resource_id=str(loaded_config.version),
            )
        except (OSError, ValidationError, json.JSONDecodeError):
            logger.exception("Runtime config could not be loaded; keeping old config")
            _audit_event(
                "runtime_config.reload_failed",
                "failure",
                resource_type="runtime_config",
            )

    try:
        init_db()
    except Exception:
        logger.exception("Database initialization failed")


@app.get("/health")
async def health_check():
    """Liveness probe - checks if application is running"""
    return {"status": "healthy", "service": "todo-service"}


@app.get("/api/v1/config", response_model=RuntimeConfig)
async def read_runtime_config():
    """Public demo endpoint for observing the active in-memory configuration."""
    return get_runtime_config()


@app.post("/api/v1/admin/reload-config", response_model=RuntimeConfig)
async def reload_runtime_config(request: Request):
    """Reload runtime config; only the sidecar on this pod may call this endpoint."""
    client_host = request.client.host if request.client else None
    if client_host not in {"127.0.0.1", "::1"}:
        raise HTTPException(
            status_code=403, detail="Reload is only allowed from localhost"
        )

    try:
        loaded_config = load_runtime_config()
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=503, detail="Runtime config file not found"
        ) from exc
    except (OSError, ValidationError, json.JSONDecodeError) as exc:
        logger.exception("Runtime config reload failed; keeping old config")
        _audit_event(
            "runtime_config.reload_failed",
            "failure",
            resource_type="runtime_config",
        )
        raise HTTPException(
            status_code=422, detail="Runtime config is invalid"
        ) from exc

    _audit_event(
        "runtime_config.reloaded",
        "success",
        resource_type="runtime_config",
        resource_id=str(loaded_config.version),
    )
    return loaded_config


@app.get("/ready")
async def readiness_check():
    """Readiness probe - checks if application can handle traffic (DB connection)"""
    try:
        # Test database connection
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        cursor.close()
        conn.close()

        return {"status": "ready", "service": "todo-service", "database": "connected"}
    except Exception:
        logger.exception("Readiness database check failed")
        # Database not ready - return 503 Service Unavailable
        raise HTTPException(
            status_code=503,
            detail={
                "status": "not_ready",
                "service": "todo-service",
                "database": "disconnected",
            },
        )


@app.post("/api/v1/todos", response_model=Todo)
async def create_todo(todo: TodoCreate, user_id: int = Depends(verify_token)):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO todos (title, description, user_id) "
            "VALUES (%s, %s, %s) RETURNING *",
            (todo.title, todo.description, user_id),
        )
        created_todo = cursor.fetchone()
        conn.commit()
        _audit_event(
            "todo.created",
            "success",
            actor_id=user_id,
            resource_type="todo",
            resource_id=created_todo["id"],
        )

        return Todo(
            id=created_todo["id"],
            title=created_todo["title"],
            description=created_todo["description"],
            completed=bool(created_todo["completed"]),
            user_id=created_todo["user_id"],
            created_at=str(created_todo["created_at"]),
        )
    finally:
        cursor.close()
        conn.close()


@app.get("/api/v1/todos", response_model=List[Todo])
async def get_todos(user_id: int = Depends(verify_token)):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT * FROM todos WHERE user_id = %s ORDER BY created_at DESC",
            (user_id,),
        )
        todos = cursor.fetchall()

        return [
            Todo(
                id=todo["id"],
                title=todo["title"],
                description=todo["description"],
                completed=bool(todo["completed"]),
                user_id=todo["user_id"],
                created_at=str(todo["created_at"]),
            )
            for todo in todos
        ]
    finally:
        cursor.close()
        conn.close()


@app.get("/api/v1/todos/{todo_id}", response_model=Todo)
async def get_todo(todo_id: int, user_id: int = Depends(verify_token)):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(SQL_GET_TODO_BY_ID_AND_USER, (todo_id, user_id))
        todo = cursor.fetchone()

        if not todo:
            raise HTTPException(status_code=404, detail=ERROR_TODO_NOT_FOUND)

        return Todo(
            id=todo["id"],
            title=todo["title"],
            description=todo["description"],
            completed=bool(todo["completed"]),
            user_id=todo["user_id"],
            created_at=str(todo["created_at"]),
        )
    finally:
        cursor.close()
        conn.close()


@app.patch("/api/v1/todos/{todo_id}", response_model=Todo)
async def update_todo(
    todo_id: int, todo_update: TodoUpdate, user_id: int = Depends(verify_token)
):
    conn = get_db()
    cursor = conn.cursor()
    try:
        # Check if todo exists and belongs to user
        cursor.execute(SQL_GET_TODO_BY_ID_AND_USER, (todo_id, user_id))
        existing = cursor.fetchone()

        if not existing:
            raise HTTPException(status_code=404, detail=ERROR_TODO_NOT_FOUND)

        # Update fields
        update_data = todo_update.model_dump(exclude_unset=True)

        if update_data:
            set_clause = ", ".join([f"{key} = %s" for key in update_data.keys()])
            values = list(update_data.values()) + [todo_id, user_id]

            cursor.execute(
                f"UPDATE todos SET {set_clause} WHERE id = %s AND user_id = %s", values
            )
            conn.commit()
            _audit_event(
                "todo.updated",
                "success",
                actor_id=user_id,
                resource_type="todo",
                resource_id=todo_id,
                changed_fields=list(update_data.keys()),
            )

        # Get updated todo
        cursor.execute(SQL_GET_TODO_BY_ID_AND_USER, (todo_id, user_id))
        updated_todo = cursor.fetchone()

        return Todo(
            id=updated_todo["id"],
            title=updated_todo["title"],
            description=updated_todo["description"],
            completed=bool(updated_todo["completed"]),
            user_id=updated_todo["user_id"],
            created_at=str(updated_todo["created_at"]),
        )
    finally:
        cursor.close()
        conn.close()


@app.delete("/api/v1/todos/{todo_id}")
async def delete_todo(todo_id: int, user_id: int = Depends(verify_token)):
    conn = get_db()
    cursor = conn.cursor()
    try:
        # Check if todo exists and belongs to user
        cursor.execute(
            "SELECT id FROM todos WHERE id = %s AND user_id = %s", (todo_id, user_id)
        )
        existing = cursor.fetchone()

        if not existing:
            raise HTTPException(status_code=404, detail=ERROR_TODO_NOT_FOUND)

        cursor.execute(
            "DELETE FROM todos WHERE id = %s AND user_id = %s", (todo_id, user_id)
        )
        conn.commit()
        _audit_event(
            "todo.deleted",
            "success",
            actor_id=user_id,
            resource_type="todo",
            resource_id=todo_id,
        )

        return {"message": "Todo deleted successfully"}
    finally:
        cursor.close()
        conn.close()


@app.get("/api/v1/admin/todos", response_model=List[Todo])
async def get_all_todos(current_user_id: int = Depends(verify_token)):
    """Admin endpoint to get all todos (requires authentication)"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM todos ORDER BY created_at DESC")
        todos = cursor.fetchall()

        return [
            Todo(
                id=todo["id"],
                title=todo["title"],
                description=todo["description"],
                completed=bool(todo["completed"]),
                user_id=todo["user_id"],
                created_at=str(todo["created_at"]),
            )
            for todo in todos
        ]
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8002)
