# Homelab App

Homelab App is a small service-oriented todo application. It has a React/Vite
frontend, a FastAPI user service, a FastAPI todo service, and one PostgreSQL
database for each backend service.

The frontend never connects directly to PostgreSQL. Every user action follows
this path:

~~~text
Browser
  |
  +-- UI route: /login, /register, /todos
  |
  +-- API request: /api/v1/...
          |
          +-- local development: Vite proxy
          +-- Kubernetes: Gateway API / HTTPRoute
                    |
                    +-- user-service -> user database
                    +-- todo-service -> todo database
~~~

## Application Components

| Component | Responsibility | Local port |
| --- | --- | ---: |
| frontend | React UI, routing, session and server-state handling | 5173 |
| user-service | Registration, login, JWT validation and user records | 8001 |
| todo-service | Authenticated todo CRUD and todo records | 8002 |
| user-db | PostgreSQL database owned by user-service | 5432 |
| todo-db | PostgreSQL database owned by todo-service | 5433 on host, 5432 in Compose |

The local databases run as the user-db and todo-db services in
.devcontainer/compose.yaml. The backend processes run inside the workspace
container and connect to those databases over the private Compose network.

## Database Ownership

Each service owns its own database and table. There is no shared application
database and no cross-service SQL join.

| Service | Local database URL | Table | Stored data |
| --- | --- | --- | --- |
| user-service | postgresql://userservice:userpass@user-db:5432/userdb | users | User id, username, email and bcrypt password hash |
| todo-service | postgresql://todoservice:todopass@todo-db:5432/tododb | todos | Todo id, title, description, completion state, owner id and creation time |

In staging and production, the same ownership model is used. The actual
connection is supplied through each deployment's DATABASE_URL environment
variable, so each service connects to its environment-specific PostgreSQL
workload rather than to the other service's database.

The tables are created by each service's startup init_db() function with
CREATE TABLE IF NOT EXISTS. This is a small demonstration schema initializer,
not a versioned migration system.

### users table

~~~sql
id             SERIAL PRIMARY KEY
username       VARCHAR(255) UNIQUE NOT NULL
email          VARCHAR(255) UNIQUE NOT NULL
hashed_password TEXT NOT NULL
~~~

### todos table

~~~sql
id          SERIAL PRIMARY KEY
title       VARCHAR(255) NOT NULL
description TEXT
completed   BOOLEAN DEFAULT FALSE
user_id     INTEGER NOT NULL
created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
~~~

todos.user_id is the user id from the JWT. It is not a PostgreSQL foreign key
to the users table because the tables belong to different service databases.
The todo service currently authorizes ownership from the token and its own
todos table.

## API Namespace

All application API endpoints use the /api/v1 namespace. Browser pages use
different paths, so a browser route can never be mistaken for an API route.

### User service endpoints

| Method | Endpoint | Purpose | Authentication |
| --- | --- | --- | --- |
| POST | /api/v1/auth/register | Create a user | None |
| POST | /api/v1/auth/login | Verify credentials and issue a JWT | None |
| GET | /api/v1/auth/me | Validate the JWT and return the current user | Bearer token |
| GET | /api/v1/users/{id} | Read a user by id | Currently public |
| GET | /api/v1/admin/users | List all users | Bearer token, no role check yet |
| POST | /api/v1/admin/create-admin | Create the default admin record | Bearer token, no role check yet |
| GET | /health | Liveness response | None |

### Todo service endpoints

| Method | Endpoint | Purpose | Authentication |
| --- | --- | --- | --- |
| POST | /api/v1/todos | Create a todo for the token owner | Bearer token |
| GET | /api/v1/todos | List only the token owner's todos | Bearer token |
| GET | /api/v1/todos/{id} | Read one todo owned by the token user | Bearer token |
| PATCH | /api/v1/todos/{id} | Partially update an owned todo | Bearer token |
| DELETE | /api/v1/todos/{id} | Delete an owned todo | Bearer token |
| GET | /api/v1/admin/todos | List all todos | Bearer token, no role check yet |
| GET | /api/v1/config | Read the current runtime demo config | None |
| POST | /api/v1/admin/reload-config | Reload runtime config from the mounted file | Localhost only |
| GET | /health | Liveness response | None |
| GET | /ready | Check database connectivity | None |

### API response boundary and validation

Unknown `/api/*` paths must return an API error, not the frontend's
`index.html`. Vite sends the `/api/v1` fallback to a backend during local
development, while Caddy returns `404` for API paths that reach the frontend
container. The centralized API client also requires a JSON response, so an
HTML `200` response cannot be mistaken for a successful API call or a login
token response.

The todo service validates titles at the API boundary. A title must contain
non-whitespace text and be at most 255 characters. `PATCH` rejects an explicit
`null` or blank title, while omitted fields remain unchanged. Invalid payloads
return FastAPI's standard `422` validation response instead of reaching SQL
and producing a database error.

## Registration Flow

1. The user opens /register and submits username, email and password.
2. LoginPage sends POST /api/v1/auth/register through the centralized API
   client.
3. Vite forwards the request to user-service locally. In Kubernetes, the
   Gateway routes the /api/v1/auth path to user-service.
4. FastAPI validates the request body with UserCreate.
5. user-service queries users for an existing username or email. A match
   returns 409 Conflict.
6. The password is hashed with bcrypt. The plain password is not stored.
7. The service inserts the new row into userdb.users, commits the transaction,
   and returns the new user's id, username and email.
8. Registration does not issue a JWT. The frontend navigates to /login, and
   the user must authenticate explicitly.

## Login Flow

1. The user opens /login and submits a username and password.
2. The frontend sends POST /api/v1/auth/login.
3. user-service selects the user by username from users and compares the
   submitted password with hashed_password using bcrypt.
4. Missing users and wrong passwords return 401 Unauthorized.
5. For valid credentials, the service creates an HS256 JWT containing:
   - sub: the username;
   - user_id: the numeric user id;
   - exp: an expiry 30 minutes in the future.
6. The response contains { "access_token": "...", "token_type": "bearer" }.
   It deliberately does not fabricate or return a frontend user object.
7. The frontend stores only the token in localStorage under token and moves
   to /todos.

## Session Bootstrap And Token Validation

The token in localStorage is not treated as proof that the user is logged in.
On application startup, AuthProvider runs the session React Query:

~~~text
localStorage.token
        |
        +-- GET /api/v1/auth/me
                Authorization: Bearer <token>
~~~

user-service verifies the Bearer header, JWT signature, algorithm, expiry and
user_id. It then reads the user from users and returns the real user data.
Only after this request succeeds does the frontend consider the user
authenticated. While it is pending, the UI displays an initialization state.

If the token is expired, malformed, rejected, or the user no longer exists,
the session is cleared and the user is sent to /login. A failed request is
not silently ignored. The same behavior applies to any later API request that
returns 401.

Logout is client-side in this iteration: the token and the legacy local user
entry are removed, the session and todos query data are removed, and the
browser navigates to /login.

## Todo Flow

All todo operations use the token owner returned by verify_token. The client
cannot choose another user_id in the request body.

### Create a todo

1. A signed-in user submits the form on /todos.
2. The frontend sends:

~~~http
POST /api/v1/todos
Authorization: Bearer <token>
Content-Type: application/json

{"title":"...", "description":"..."}
~~~

3. FastAPI validates TodoCreate.
4. todo-service verifies the JWT and extracts user_id.
5. It inserts title, description and the token's user_id into tododb.todos;
   PostgreSQL supplies id, completed and created_at.
6. The transaction is committed and the created todo is returned.
7. The frontend invalidates the todos React Query entry, so the list is
   fetched again from the server.

### Read todos

GET /api/v1/todos verifies the token and executes a query equivalent to:

~~~sql
SELECT * FROM todos
WHERE user_id = <user_id from JWT>
ORDER BY created_at DESC;
~~~

This is why one user does not see another user's todos. The UI shows loading,
error and empty-list states instead of treating a failed request as an empty
list.

### Read one todo

GET /api/v1/todos/{id} checks both id and the JWT user_id. A todo owned by
another user is not returned and produces 404 Todo not found.

### Partially update a todo

The frontend uses PATCH /api/v1/todos/{id}. The request may contain any
subset of title, description and completed:

~~~json
{"completed": true}
~~~

The Pydantic model uses exclude_unset=True, so omitted fields are left alone.
An explicitly supplied null description is therefore different from an
omitted description. The service first checks ownership, updates only supplied
fields, commits, and returns the updated row. The frontend invalidates the
todos query after success.

### Delete a todo

DELETE /api/v1/todos/{id} verifies the token and ownership before deleting
from tododb.todos. After a successful response, the frontend invalidates the
todo query and renders the refreshed list.

## Frontend State And Routing

React Router owns browser navigation:

| Browser path | Behavior |
| --- | --- |
| / | Redirects to /todos when the session is valid, otherwise /login |
| /login | Guest login page; authenticated users are redirected to /todos |
| /register | Guest registration page |
| /todos | Protected todo page |
| any other UI path | Small not-found page |

API requests always start with /api/v1. They are not React Router routes.
The centralized frontend/src/api/client.js adds the namespace, attaches the
Bearer token, parses FastAPI detail errors, and invokes the logout handler on
401.

React Query owns server state:

| Query or mutation | Server operation |
| --- | --- |
| session query | GET /api/v1/auth/me during bootstrap |
| todos query | GET /api/v1/todos while authenticated |
| create mutation | POST /api/v1/todos |
| update mutation | PATCH /api/v1/todos/{id} |
| delete mutation | DELETE /api/v1/todos/{id} |

The frontend does not keep a second fabricated copy of the user or todos. It
uses the API response as the source of truth and invalidates the todo query
after successful mutations.

## Local Request Routing

During local development, Caddy is not involved. Vite serves the UI and its
development proxy sends API paths to the correct FastAPI process:

~~~text
Browser -> Vite :5173
  /api/v1/auth/*, /api/v1/users/* -> user-service :8001
  /api/v1/todos/*, /api/v1/config -> todo-service :8002
~~~

The backend processes use Uvicorn with --reload, and Vite uses HMR. Source
changes are therefore visible without rebuilding the workspace image.

In staging and production, the frontend image contains the built React SPA and
Caddy serves it on port 3000. Caddy's try_files fallback returns index.html
for UI deep links such as /todos. The Kubernetes Gateway API routes
/api/v1/auth and user paths to user-service, todo paths to todo-service, and
the remaining UI path to the frontend. This keeps API paths and browser paths
separate in the deployed environment too.

## Local Development

The complete local environment is described in .devcontainer/README.md.
The short flow is:

1. Reopen the repository in the Dev Container.
2. Wait for the two PostgreSQL Compose services and dependency setup.
3. Run Tasks: Run Task > Dev: Start all.
4. Open http://localhost:5173.

The first request to /register creates data in user-db. After login, the
todo page reads and writes data in todo-db; the two database containers do
not share data.

Useful checks from the workspace container:

~~~bash
user-service/.venv/bin/pytest user-service
todo-service/.venv/bin/pytest todo-service
npm --prefix frontend run lint
npm --prefix frontend test
npm --prefix frontend run build
~~~

### Current Python Dependency Workflow

Each backend is an independent uv project with its own `pyproject.toml` and
`uv.lock`. This matches the separate Docker build contexts and allows either
service to move to its own repository later without splitting a root lockfile.

Preferred commands are:

~~~bash
uv sync --project user-service --locked
uv sync --project todo-service --locked
uv run --project user-service --locked pytest user-service
uv run --project todo-service --locked pytest todo-service
ruff format --check --diff user-service todo-service
ruff check user-service todo-service
~~~

Production Docker builds use `uv sync --locked --no-dev`. CI creates a fresh
service `.venv` for every workspace and persists only uv's download/build
cache. Trivy reads each standard `uv.lock` directly.

The Python library migrations are:

| Previous | Current |
| --- | --- |
| pip + manually created venv | uv project sync and lockfiles |
| Black + Flake8 | Ruff formatter + linter |
| python-jose | PyJWT with an explicit `HS256` decode allow-list |
| Passlib CryptContext | direct bcrypt hashing and verification |
| psycopg2 + RealDictCursor | psycopg3 + `dict_row` |

A fixed hash generated before the Passlib removal is covered by tests to prove
that existing standard bcrypt hashes still verify.

### Legacy pip And Lint Compatibility

The uv/Ruff path above is the active development and CI implementation. The
previous pip, Black, and Flake8 inputs remain available for users that need the
older workflow:

| File | Compatibility purpose |
| --- | --- |
| `pyproject.toml` | Root legacy Black configuration |
| `.flake8` | Legacy Flake8 lint configuration |
| `<service>/requirements.txt` | Current runtime dependencies in pip format |
| `<service>/requirements-test.txt` | Runtime plus test dependencies for pip |

The compatibility requirements use the current PyJWT, bcrypt, and psycopg3
dependencies, so they still execute today's application code. They are not
used by the active Dev Container, production Dockerfiles, or Jenkins uv steps;
`pyproject.toml` and `uv.lock` inside each service remain canonical. When a
dependency changes, update the matching pip compatibility files as part of the
same commit to prevent the two supported installation paths from drifting.

The repository no longer carries a `Dockerfile.test`. The supported local and
CI test path is uv with the service-local `pyproject.toml` and `uv.lock`.

## Application Logging And Telemetry

Both FastAPI services write one compact JSON record per log event to stdout.
They do not write log files. Kubernetes captures stdout in the container
runtime format; Grafana Alloy removes that outer CRI/Docker envelope, parses
the JSON, adds Kubernetes metadata, and forwards the record to Elasticsearch.
`OTEL_LOGS_EXPORTER=none` remains intentional: application logs follow the
stdout collection path, while OpenTelemetry continues to export traces.

Each service owns a small `logging_config.py`. It configures the root,
application, and Uvicorn error loggers, disables ordinary Uvicorn access-log
lines, and keeps one request-completion event per request. The containers and
development tasks therefore pass Uvicorn's `--no-access-log` option. This does
not disable access control or application errors; it only removes Uvicorn's
duplicate plain-text line because the application middleware already emits the
structured JSON request event. Without it, one request would normally produce
both a plain Uvicorn access line and the JSON `http.request.completed` record.

Health, readiness, and metrics endpoints are intentionally quiet on successful
requests. This avoids flooding pod logs with Kubernetes probes and Prometheus
scrapes; it does not disable the endpoints. A non-2xx probe result is logged so
failed probes remain diagnosable. A failed readiness check also records the
database exception on the server side, while Kubernetes exposes the probe
result through Pod conditions and Events (`kubectl describe pod`), and the raw
exception is not returned to the client. `/metrics` is a scrape response, not
an application log record.

The request event is emitted after the response:

| Result | Severity | Event |
| --- | --- | --- |
| successful non-health request | `INFO` | `http.request.completed` |
| expected 4xx response | `WARNING` | `http.request.completed` |
| 5xx response or unexpected exception | `ERROR` | `http.request.completed` or `http.request.failed` |

Authentication and administrative actions additionally emit audit events:

| Event | Meaning |
| --- | --- |
| `user.registered` | A user was created |
| `auth.login_succeeded` / `auth.login_failed` | Login outcome |
| `auth.token_rejected` | A bearer token was missing or invalid |
| `todo.created` / `todo.updated` / `todo.deleted` | Todo mutation; updates list only changed field names |
| `admin.users_listed` / `admin.created` | Administrative operation |
| `runtime_config.reloaded` / `runtime_config.reload_failed` | Runtime configuration reload outcome |

Records include UTC RFC3339 timestamps, severity, logger, service identity,
deployment environment, outcome, HTTP method/route/status/duration, actor ID
when known, resource identifiers when applicable, exception details for
server-side failures, and OpenTelemetry `trace_id`, `span_id`, and sampling
state when a span is active. `OTEL_RESOURCE_ATTRIBUTES` supplies the service
identity used by both traces and logs; Helm sets the service, namespace,
actual image tag, environment, and cluster attributes.

In the Dev Container, `OTEL_SDK_DISABLED=false` keeps local span creation and
log correlation enabled, while `OTEL_TRACES_EXPORTER=none` disables only trace
export because no local Collector is running. Kubernetes deployments set an
OTLP endpoint and use the `otlp` exporter, so their spans continue through
Alloy to Jaeger.

The formatter allow-lists fields and redacts token/password/secret values and
email addresses. It never logs request bodies, JWTs, passwords, email
addresses, or todo content. Alloy keeps low-cardinality fields such as
`service_name`, `event_name`, and `outcome` as searchable labels, while trace,
actor, resource, route, duration, changed-field, and exception values remain
structured metadata rather than index labels.

Useful Kibana queries include:

~~~text
service_name: "user-service" and event_name: "auth.login_failed"
service_name: "todo-service" and event_name: "todo.updated"
actor_id: 7 and event_name: "todo.deleted"
trace_id: "<trace-id>"
~~~

## API Migration

The API was moved under an explicit versioned namespace and todo updates were
changed to real partial updates:

| Previous shape | Current shape |
| --- | --- |
| /register | /api/v1/auth/register |
| /login | /api/v1/auth/login |
| session verification endpoint | /api/v1/auth/me |
| /users/{id} | /api/v1/users/{id} |
| /todos | /api/v1/todos |
| /todos/{id} with full replacement semantics | PATCH /api/v1/todos/{id} |
| /admin/... | /api/v1/admin/... |

Clients using the old unnamespaced paths must be updated. The frontend proxy,
Kubernetes HTTPRoutes and Helm templates use the new paths.

## Current Security Notes

These are known limitations of the current application and are intentionally
visible here rather than hidden by the pipeline:

- Both services have a fallback JWT secret in source code if SECRET_KEY is
  missing. Production must inject a strong secret and fail closed when it is
  absent.
- CORS currently allows every origin with wildcard methods and headers. It
  should be restricted to the deployed frontend origin.
- GET /api/v1/users/{id} is public and exposes user profile fields.
- Admin endpoints only require a valid JWT. There is no role claim or role
  authorization yet.
- Both services validate HS256 tokens with the same shared secret. A compromise
  of either service can therefore affect token trust across both services.

The initial admin endpoint also returns the generated default password for
setup convenience. That behavior should be removed or replaced with a secure
one-time administration flow before production use.
