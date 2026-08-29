import os
from datetime import datetime, timedelta
from typing import List

import psycopg2
import psycopg2.extras  # Import extras explicitly for RealDictCursor
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from jose import JWTError, jwt

# OpenTelemetry SDK and Instrumentation
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from passlib.context import CryptContext
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel

# Configure OpenTelemetry SDK
resource = Resource.create(
    {
        "service.name": os.getenv("OTEL_SERVICE_NAME", "user-service"),
    }
)

trace.set_tracer_provider(TracerProvider(resource=resource))
otlp_exporter = OTLPSpanExporter()
span_processor = BatchSpanProcessor(otlp_exporter)
trace.get_tracer_provider().add_span_processor(span_processor)

# Enable psycopg2 instrumentation BEFORE any db connections
Psycopg2Instrumentor().instrument()


app = FastAPI(title="User Service", version="1.0.0")

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

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class UserCreate(BaseModel):
    username: str
    email: str
    password: str


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
    conn = psycopg2.connect(database_url, cursor_factory=psycopg2.extras.RealDictCursor)
    return conn


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
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def verify_token(authorization: str = Header(None)):
    """Verify JWT token and return user_id"""
    scheme, separator, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not separator or not token.strip():
        raise HTTPException(status_code=401, detail="Invalid authorization header")

    try:
        payload = jwt.decode(token.strip(), SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("user_id")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return user_id
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


@app.on_event("startup")
async def startup_event():  # pragma: no cover
    try:
        init_db()
    except Exception:
        # In test environment, database might not be available
        pass


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
            raise HTTPException(status_code=401, detail="Invalid credentials")

        access_token = create_access_token(
            data={"sub": user["username"], "user_id": user["id"]}
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
