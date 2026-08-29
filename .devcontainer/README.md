# Development Environment

Reproducible VS Code Dev Container for Homelab App: two Python services, a
Vite frontend, and two local PostgreSQL databases. Source code remains in the
Windows repository; development tools, dependencies, and databases run in
Docker.

## Quick Start

### First Creation

1. Start Docker Desktop.
2. Install the **Dev Containers** extension in VS Code.
3. Open this directory in regular Windows VS Code:

   ```text
   C:\Users\kerem\Documents\infrastructure\App
   ```

4. Press `Ctrl+Shift+P` and select **Dev Containers: Reopen in Container**.
5. Wait for the initial build and dependency installation to finish:

   ```text
   Development dependencies are ready. Run the 'Dev: Start all' VS Code task.
   ```

6. Press `Ctrl+Shift+P`, select **Tasks: Run Task**, then select
   **Dev: Start all**.
7. Open `http://localhost:5173`.

Do not search for `Dev: Start all` directly in the command palette. It is a
workspace task and appears after selecting **Tasks: Run Task**. The same list
is available from **Terminal > Run Task**.

### Application Ports

| Process | Port | URL |
| --- | ---: | --- |
| Frontend (Vite) | `5173` | `http://localhost:5173` |
| User Service | `8001` | `http://localhost:8001` |
| Todo Service | `8002` | `http://localhost:8002` |

VS Code forwards these ports from the `workspace` container. A forwarded port
returns `ECONNREFUSED` until **Dev: Start all** has started the corresponding
application process.

Each development server occupies a task terminal and continuously prints logs.
Use the terminal panel's **+** button for a separate interactive shell. Pressing
`Ctrl+C` in a task terminal stops only that server.

### Later Starts

Dependencies and database data persist in Docker named volumes. For a normal
later session:

1. Select **Dev Containers: Reopen in Container**.
2. Select **Tasks: Run Task > Dev: Start all**.

The image and dependencies are reused.

## Common Actions

| Need | Command or VS Code action |
| --- | --- |
| Start the environment | **Dev Containers: Reopen in Container** |
| Start all application processes | **Tasks: Run Task > Dev: Start all** |
| Open an interactive container shell | **Terminal > New Terminal** |
| Run Python tests | **Tasks: Run Task > Test: Python services** |
| Run all lint checks | **Tasks: Run Task > Lint: All** |
| Stop one application process | `Ctrl+C` in that process's task terminal |
| Stop the complete environment | **Dev Containers: Reopen Folder Locally**, close the attached window, or use the `stop` command below |
| Remove containers and network but retain data | Use the `down` command below |
| Full reset, including dependencies and databases | Use `down --volumes` below |

Run explicit Compose lifecycle commands from the `App` directory:

```bash
# Stop workspace and both databases; retain everything for a fast restart.
docker compose --project-name app_devcontainer -f .devcontainer/compose.yaml stop

# Remove containers and the Compose network; retain named volumes and images.
docker compose --project-name app_devcontainer -f .devcontainer/compose.yaml down

# Full reset: also delete venvs, node_modules, caches, and database data.
docker compose --project-name app_devcontainer -f .devcontainer/compose.yaml down --volumes
```

For normal daily shutdown, use `stop`. The final command intentionally deletes
all local PostgreSQL data.

## Change Guide

| Change | Required action |
| --- | --- |
| Python, JSX, CSS, or other source | Save the file; Uvicorn reload or Vite HMR handles it |
| `frontend/vite.config.js` | Restart the `Dev: Frontend` task; Vite reads its server configuration only at startup |
| `requirements-test.txt` | Rerun `bash .devcontainer/post-create.sh` or install into the relevant venv |
| `package-lock.json` | Run `npm --prefix frontend ci` |
| Dockerfile, Node Feature, Compose, or Dev Container settings | **Dev Containers: Rebuild Container** |

Normal source changes do not rebuild a Docker image. The Windows `App`
directory is bind-mounted into the container, so saved files are immediately
visible under `/workspace`.

## Architecture And Internals

The remaining sections explain why the environment is designed this way and
what VS Code and Docker do behind the scenes. They are reference material, not
prerequisites for the quick start.

### System Overview

```text
Windows
  VS Code UI
  App source directory
  Docker Desktop
        |
        | creates the Compose project
        v
app_devcontainer
  workspace container
    VS Code Server
    User Service process
    Todo Service process
    Vite process
    Python and Node development tools

  user-db container
  todo-db container
```

The complete Compose project is the local development environment. Only the
`workspace` service is the primary container to which VS Code attaches.

### Dev Container And Compose Relationship

A Dev Container is not a special container type. `.devcontainer` is a
conventional configuration directory discovered by the Dev Containers
extension. Its `devcontainer.json` connects VS Code to Compose:

```json
"dockerComposeFile": "compose.yaml",
"service": "workspace",
"workspaceFolder": "/workspace"
```

- `dockerComposeFile` selects `.devcontainer/compose.yaml` relative to
  `devcontainer.json`.
- `service` selects the Compose service that hosts VS Code, terminals,
  extensions, tasks, and application processes.
- `workspaceFolder` selects the project directory opened inside that container.

The Compose YAML does not run inside the container. The Dev Containers
extension invokes Docker Compose through Docker Desktop on Windows. Docker
Compose asks the Docker Engine to create:

```text
app_devcontainer
  +-- workspace   <- primary Dev Container
  +-- user-db     <- PostgreSQL sidecar
  +-- todo-db     <- PostgreSQL sidecar
```

Paths in `compose.yaml` are relative to its `.devcontainer` directory:

```yaml
build:
  context: .
  dockerfile: Dockerfile
```

This selects `.devcontainer/Dockerfile`. The source mount:

```yaml
volumes:
  - ..:/workspace:cached
```

mounts the parent `App` directory from Windows at `/workspace`. `cached` is a
Docker Desktop consistency/performance hint, not a dependency cache.

The extension may create temporary Compose overrides on the host. They add
Dev Container Features, identifying labels, VS Code Server setup, and lifecycle
details on top of the repository's Compose definition.

### Local VS Code And Remote Execution

The VS Code interface remains a Windows application. The extension installs a
VS Code Server in the `workspace` container and connects the window to it:

```text
VS Code UI on Windows
        |
        | remote connection
        v
VS Code Server in workspace
        +-- integrated terminals run here
        +-- shell tasks run here
        +-- container-side extensions run here
        +-- /workspace is opened here
```

This remote connection makes tasks run in the container. The
`${workspaceFolder}` variable does not choose the execution machine; it only
resolves to the current workspace path. In this environment:

```json
"cwd": "${workspaceFolder}/user-service"
```

becomes:

```text
/workspace/user-service
```

If the repository is reopened locally, tasks execute in the local context and
`${workspaceFolder}` becomes the Windows repository path.

### Lifecycle: Create, Reopen, Start

The files do not all execute on every reopen.

#### First Creation Or Rebuild

```text
Dev Containers extension reads devcontainer.json
        |
        +-- Compose reads compose.yaml
        |     +-- builds workspace from Dockerfile
        |     +-- starts both databases
        |     +-- mounts source and named volumes
        |
        +-- installs the Node Feature and VS Code extensions
        +-- attaches VS Code to workspace
        +-- runs post-create.sh
              +-- creates two Python venvs
              +-- installs Python dependencies and lint tools
              +-- runs npm ci
```

At this point the environment is ready, but Uvicorn and Vite are not running.

#### Normal Reopen

```text
read devcontainer.json
        |
start existing Compose services if stopped
        |
attach VS Code to /workspace
        |
activate port forwarding and container-side extensions
```

The Dockerfile is not rebuilt, the Node Feature is not reinstalled, and
`post-create.sh` does not run when an existing container is simply reopened.

#### Application Start

Once `/workspace` is open, VS Code discovers `/workspace/.vscode/tasks.json`.
Selecting `Dev: Start all` follows its `dependsOn` list:

```text
.vscode/tasks.json
  +-- Dev: User service
  |     +-- user-service/.venv/bin/uvicorn
  |           +-- imports user-service/app.py
  |
  +-- Dev: Todo service
  |     +-- todo-service/.venv/bin/uvicorn
  |           +-- imports todo-service/app.py
  |
  +-- Dev: Frontend
        +-- npm run dev
              +-- package.json starts Vite
                    +-- Vite reads vite.config.js
```

Only now do ports `5173`, `8001`, and `8002` have listening processes.

### Repository File Map

| File | Read or executed by | Responsibility |
| --- | --- | --- |
| `.devcontainer/devcontainer.json` | Dev Containers extension | Selects Compose, primary service, workspace, Features, extensions, forwarded ports, and lifecycle command |
| `.devcontainer/compose.yaml` | Docker Compose on the host | Defines workspace, databases, networking, mounts, health checks, and named volumes |
| `.devcontainer/Dockerfile` | Docker builder | Creates the OS-level workspace image |
| `.devcontainer/post-create.sh` | Dev Containers lifecycle | Installs repository dependencies after a new container is created |
| `.vscode/tasks.json` | VS Code Tasks | Defines start, test, and lint commands |
| `frontend/vite.config.js` | Vite after `npm run dev` | Binds the dev server and proxies local API routes |
| `.gitignore` | Git | Excludes generated development files |
| `.flake8` | Flake8 | Excludes venv content from application linting |

### File Details

#### `devcontainer.json`

Besides selecting Compose and `workspace`, this file:

- starts `workspace`, `user-db`, and `todo-db` through `runServices`;
- installs Node.js `20.20.2` as a Dev Container Feature;
- installs Python, ESLint, and YAML VS Code extensions in the remote context;
- forwards ports `5173`, `8001`, and `8002`;
- runs `post-create.sh` after container creation;
- sets `shutdownAction` to `stopCompose`.

`stopCompose` stops the three Compose services when the last attached editor
window disconnects. It retains containers, images, and named volumes.

#### `compose.yaml`

The `workspace` service contains development runtimes and tools. Its
`sleep infinity` command keeps the container alive for VS Code; it does not
start the application.

`user-db` and `todo-db` are PostgreSQL 15 sidecars. Compose waits for their
health checks before starting `workspace`. Service names become DNS names on
the private Compose network, which is why application URLs use values such as:

```text
postgresql://userservice:userpass@user-db:5432/userdb
```

#### `Dockerfile`

The workspace image starts from the Microsoft Python 3.11 Dev Container image
and adds compiler tools, PostgreSQL client headers for `psycopg2`, and `psql`.
It does not copy source or install repository dependencies. Source is mounted
by Compose and dependencies are installed after creation.

Node.js is added by the Feature in `devcontainer.json`, not by the Dockerfile.

#### `post-create.sh`

This script runs automatically after a new container is created. It:

1. creates `user-service/.venv` and `todo-service/.venv`;
2. installs each service's `requirements-test.txt`;
3. installs Black, Flake8, and Ruff;
4. runs frontend `npm ci` from the lock file.

The base image is not empty before this script. It already contains Linux,
Python, Git, shell tools, PostgreSQL client tools, and the Node Feature.

#### `tasks.json`

The Tasks system exposes:

| Task | Behavior |
| --- | --- |
| `Dev: User service` | Uvicorn with reload on `8001` and User Service environment variables |
| `Dev: Todo service` | Uvicorn with reload on `8002` and Todo Service environment variables |
| `Dev: Frontend` | Vite with HMR on `5173` |
| `Dev: Start all` | Starts the three development tasks in parallel |
| `Test: Python services` | Runs both Python test suites |
| `Lint: All` | Runs Black, Flake8, and frontend ESLint |

Task `env` entries apply only to the process started by that task. They do not
install dependencies or permanently modify the container.

#### `vite.config.js`

The frontend uses relative API routes. Kubernetes Gateway API routes them in
staging and production, but there is no Gateway in front of local Vite. The
development proxy reproduces the required routing:

```text
browser -> localhost:5173/login -> Vite -> localhost:8001
browser -> localhost:5173/todos -> Vite -> localhost:8002
```

Vite HMR updates JSX, CSS and other imported source modules while the frontend
task is running. It does not reload `vite.config.js`: proxy and server settings
are read when the Vite process starts. After changing `vite.config.js`, stop
the `Dev: Frontend` task with `Ctrl+C` and run it again. A Dev Container rebuild
is not required for this config-only change.

`server.host: 0.0.0.0` makes Vite reachable through container port forwarding.
The `server` configuration affects `npm run dev`; it does not change the
production build or Caddy runtime.

### Storage And Caches

| Data | Storage | Purpose |
| --- | --- | --- |
| Repository source | Windows bind mount at `/workspace` | Host and container see the same source edits |
| `user-service/.venv` | Docker named volume | Installed User Service Python packages |
| `todo-service/.venv` | Docker named volume | Installed Todo Service Python packages |
| `frontend/node_modules` | Docker named volume | Installed frontend packages |
| pip cache | Docker named volume | Reuses downloaded Python wheels and archives |
| npm cache | Docker named volume | Reuses downloaded npm package data |
| User and Todo PostgreSQL data | Two Docker named volumes | Databases survive container restarts |

A package cache and an installed dependency directory are different:

- pip cache avoids downloading a package again; a venv contains the installed
  executable package;
- npm cache avoids downloading package archives again; `node_modules` contains
  the installed dependency tree.

Named volumes live in Docker Desktop's Linux storage, not as ordinary
directories in the repository. Inspect them with:

```bash
docker volume ls
docker volume inspect app_devcontainer_user-service-venv
```

Separate Python venvs keep the two services' packages independent. A container
isolates the development environment from Windows, but it does not isolate
Python dependencies inside itself. Per-service venvs also match CI and reduce
future work if the services move to separate repositories.

### Development Topology And Integration Tests

The daily development topology runs User Service, Todo Service, and Vite as
ordinary Linux processes in one `workspace` container. This makes the editor,
terminals, linting, tests, and all source code easy to access. Databases remain
separate containers.

Integration tests do not inherently require one application container per
service:

- service-to-database tests can use the current workspace process and database
  sidecar;
- tests of service-to-service deployment behavior benefit from separate
  application containers;
- tests of built Docker images must run those images rather than workspace
  processes.

Separate service containers test boundaries that the shared workspace does not:

- each image contains all required files and dependencies;
- each service receives the correct environment variables;
- communication uses Compose DNS and container ports instead of shared
  `localhost`;
- startup order and health checks cross real container boundaries;
- the test environment can be created cleanly and removed afterward.

Such a Compose setup would be an additional integration-test topology, not a
replacement required for daily development.

### Direct Command Reference

VS Code tasks are shortcuts. The same commands can be run in a Dev Container
terminal.

```bash
cd /workspace/user-service
DATABASE_URL=postgresql://userservice:userpass@user-db:5432/userdb \
  .venv/bin/uvicorn app:app --host 0.0.0.0 --port 8001 --reload
```

```bash
cd /workspace/todo-service
DATABASE_URL=postgresql://todoservice:todopass@todo-db:5432/tododb \
  USER_SERVICE_URL=http://localhost:8001 \
  .venv/bin/uvicorn app:app --host 0.0.0.0 --port 8002 --reload
```

```bash
cd /workspace/frontend
npm run dev -- --host 0.0.0.0
```

Tests and lint checks:

```bash
user-service/.venv/bin/pytest user-service
todo-service/.venv/bin/pytest todo-service
user-service/.venv/bin/black --check --diff user-service todo-service
user-service/.venv/bin/flake8 user-service todo-service
npm --prefix frontend run lint
```

The credentials in `compose.yaml` are intentionally local-development values
and must not be reused in staging or production.
