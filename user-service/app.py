import logging
import os
from time import perf_counter
from datetime import datetime, timedelta
from typing import List

import bcrypt
import jwt
import psycopg
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
from prometheus_fastapi_instrumentator import Instrumentator
from psycopg.rows import dict_row
from pydantic import BaseModel, field_validator


SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "user-service")
configure_logging(SERVICE_NAME)
logger = logging.getLogger(__name__)

# Configure OpenTelemetry SDK
resource = Resource.create(otel_resource_attributes(SERVICE_NAME))

trace.set_tracer_provider(TracerProvider(resource=resource))
if os.getenv("OTEL_TRACES_EXPORTER", "otlp").lower() == "otlp":
    otel_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if otel_endpoint:
        otlp_exporter = OTLPSpanExporter(endpoint=otel_endpoint)
        span_processor = BatchSpanProcessor(otlp_exporter)
        trace.get_tracer_provider().add_span_processor(span_processor)

# Enable Psycopg instrumentation before any database connections.
PsycopgInstrumentor().instrument()


app = FastAPI(title="User Service", version="1.0.0")


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

    # Keep successful probes quiet, but retain failed probe results for diagnosis.
    is_probe = request.url.path in {"/health", "/ready", "/metrics"}
    if not is_probe or response.status_code >= 400:
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
Instrumentator().instrument(app).expose(app)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30


class UserCreate(BaseModel):
    username: str
    email: str
    password: str

    @field_validator("password")
    @classmethod
    def validate_bcrypt_password_length(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("password must not exceed 72 UTF-8 bytes")
        return value


class UserLogin(BaseModel):
    username: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str


class User(BaseModel):
    id: int
    username: str
    email: str


# Database setup
def get_db():  # pragma: no cover
    """Get PostgreSQL database connection"""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable is required")
    return psycopg.connect(database_url, row_factory=dict_row)


def init_db():  # pragma: no cover
    """Initialize database schema"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(255) UNIQUE NOT NULL,
            email VARCHAR(255) UNIQUE NOT NULL,
            hashed_password TEXT NOT NULL
        )
    """
    )
    conn.commit()
    cursor.close()
    conn.close()


def verify_password(plain_password, hashed_password):
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except ValueError:
        return False


def get_password_hash(password):
    return bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt(),
    ).decode("utf-8")


def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def verify_token(request: Request, authorization: str = Header(None)):
    """Verify JWT token and return user_id"""
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
    try:
        init_db()
    except Exception:
        logger.exception("Database initialization failed")


@app.get("/health")
async def health_check():

    return {"status": "healthy", "service": "user-service"}


@app.post("/api/v1/auth/register", response_model=User)
async def register(user: UserCreate):
    conn = get_db()
    cursor = conn.cursor()
    try:
        # Check if user exists
        cursor.execute(
            "SELECT id FROM users WHERE username = %s OR email = %s",
            (user.username, user.email),
        )
        existing = cursor.fetchone()

        if existing:
            raise HTTPException(status_code=409, detail="User already exists")

        # Create user
        hashed_password = get_password_hash(user.password)
        cursor.execute(
            "INSERT INTO users (username, email, hashed_password) "
            "VALUES (%s, %s, %s) RETURNING id",
            (user.username, user.email, hashed_password),
        )
        user_id = cursor.fetchone()["id"]
        conn.commit()
        _audit_event(
            "user.registered",
            "success",
            actor_id=user_id,
            resource_type="user",
            resource_id=user_id,
        )

        return User(id=user_id, username=user.username, email=user.email)
    finally:
        cursor.close()
        conn.close()


@app.post("/api/v1/auth/login", response_model=Token)
async def login(user_login: UserLogin):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT id, username, hashed_password FROM users WHERE username = %s",
            (user_login.username,),
        )
        user = cursor.fetchone()

        if not user or not verify_password(
            user_login.password, user["hashed_password"]
        ):
            _audit_event("auth.login_failed", "failure", resource_type="auth")
            raise HTTPException(status_code=401, detail="Invalid credentials")

        access_token = create_access_token(
            data={"sub": user["username"], "user_id": user["id"]}
        )
        _audit_event(
            "auth.login_succeeded",
            "success",
            actor_id=user["id"],
            resource_type="user",
            resource_id=user["id"],
        )
        return {"access_token": access_token, "token_type": "bearer"}
    finally:
        cursor.close()
        conn.close()


@app.get("/api/v1/auth/me", response_model=User)
async def get_current_user(user_id: int = Depends(verify_token)):
    """Validate the access token and return the authenticated user."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT id, username, email FROM users WHERE id = %s", (user_id,)
        )
        user = cursor.fetchone()

        if not user:
            raise HTTPException(status_code=401, detail="Invalid session")

        return User(id=user["id"], username=user["username"], email=user["email"])
    finally:
        cursor.close()
        conn.close()


@app.get("/api/v1/users/{user_id}", response_model=User)
async def get_user(user_id: int):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT id, username, email FROM users WHERE id = %s", (user_id,)
        )
        user = cursor.fetchone()

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        return User(id=user["id"], username=user["username"], email=user["email"])
    finally:
        cursor.close()
        conn.close()


@app.get("/api/v1/admin/users", response_model=List[User])
async def get_all_users(current_user_id: int = Depends(verify_token)):
    """Admin endpoint to get all users (requires authentication)"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, username, email FROM users ORDER BY id")
        users = cursor.fetchall()
        _audit_event(
            "admin.users_listed",
            "success",
            actor_id=current_user_id,
            resource_type="user",
        )

        return [
            User(id=user["id"], username=user["username"], email=user["email"])
            for user in users
        ]
    finally:
        cursor.close()
        conn.close()


@app.post("/api/v1/admin/create-admin")
async def create_admin(current_user_id: int = Depends(verify_token)):
    """Create default admin user (requires authentication)"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        # Check if admin already exists
        cursor.execute("SELECT id FROM users WHERE username = %s", ("admin",))
        existing = cursor.fetchone()

        if existing:
            return {"message": "Admin user already exists", "username": "admin"}

        # Create admin user with password from environment variable
        default_password = os.getenv("ADMIN_DEFAULT_PASSWORD", "admin123")
        hashed_password = get_password_hash(default_password)
        cursor.execute(
            "INSERT INTO users (username, email, hashed_password) "
            "VALUES (%s, %s, %s) RETURNING id",
            ("admin", "admin@devops-todo.com", hashed_password),
        )
        user_id = cursor.fetchone()["id"]
        conn.commit()
        _audit_event(
            "admin.created",
            "success",
            actor_id=current_user_id,
            resource_type="user",
            resource_id=user_id,
        )

        return {
            "message": "Admin user created",
            "username": "admin",
            "password": default_password,  # Return for initial setup only
            "id": user_id,
        }
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)
