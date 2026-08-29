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

