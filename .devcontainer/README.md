# Development Environment

This directory defines a reproducible VS Code Dev Container for the complete
application. The source code remains in the Windows repository, while the
development tools, installed dependencies, and local PostgreSQL databases run
in Docker.

The environment has two separate lifecycles:

1. The **development environment** starts the workspace container and the two
   PostgreSQL containers.
2. The **application processes** start Uvicorn for both Python services and
   Vite for the frontend.

Opening or creating the Dev Container completes only the first lifecycle. It
does not automatically run the application. This separation keeps the
workspace available for tests, linting, migrations, and shell work without
always consuming ports for three development servers.

## First Start

1. Start Docker Desktop.
2. Install the **Dev Containers** extension in VS Code.
3. Open this directory in regular Windows VS Code:

   ```text
   C:\Users\kerem\Documents\infrastructure\App
   ```

4. Open the command palette with `Ctrl+Shift+P`.
5. Run **Dev Containers: Reopen in Container**.
6. Wait until VS Code finishes creating the environment and the terminal shows:

   ```text
   Development dependencies are ready. Run the 'Dev: Start all' VS Code task.
   ```

7. Open the command palette again and run **Tasks: Run Task** followed by
   **Dev: Start all**.
8. Open `http://localhost:5173`.

Do not search for `Dev: Start all` directly in the command palette. Task labels
are shown only after selecting **Tasks: Run Task**. The same screen is available
from the VS Code menu under **Terminal > Run Task**.

The task starts these processes in parallel:

| Process | Container port | Host URL |
| --- | ---: | --- |
| Vite frontend | `5173` | `http://localhost:5173` |
| User Service | `8001` | `http://localhost:8001` |
| Todo Service | `8002` | `http://localhost:8002` |

Each development server occupies its own task terminal and continuously prints
logs there. This is expected. Do not press `Ctrl+C` in those terminals unless
the corresponding server should be stopped. To enter commands while the
servers continue running, create a separate shell with the terminal panel's
**+** button or **Terminal > New Terminal**.

The ports are exposed through the VS Code Dev Containers port-forwarding
session. The workspace service intentionally has no Docker `ports:` entries.
Therefore, running only `docker compose up` or opening the URL before VS Code
has attached will not expose `localhost:5173`.

The forwarded ports can be inspected from VS Code's **Ports** panel. The
bottom-left status area should show that the current window is connected to
**Homelab App Development**.

## Later Starts

Named volumes preserve dependencies and database data when the containers are
stopped. On a normal later start:

1. Reopen the directory in the Dev Container.
2. Run **Dev: Start all**.

The Docker image and dependencies do not need to be recreated for every source
change.

## Stopping The Environment

The Compose-based configuration contains:

```json
"shutdownAction": "stopCompose"
```

When the last VS Code window disconnects from the primary `workspace`
container, the Dev Containers extension stops the complete Compose environment,
not only the workspace service. In this project that means `workspace`,
`user-db`, and `todo-db` are stopped together.

Use **Dev Containers: Reopen Folder Locally** when the repository should remain
open in VS Code outside the container. Closing the attached VS Code window also
triggers the shutdown action. Application processes stop, but containers,
images, named volumes, installed dependencies, caches, and PostgreSQL data are
preserved for the next reopen.

The equivalent explicit host command is:

```bash
docker compose \
  --project-name app_devcontainer \
  -f .devcontainer/compose.yaml \
  stop
```

There are three different cleanup levels:

| Action | Containers | Named volumes and database data | Images |
| --- | --- | --- | --- |
| `stop` or `shutdownAction: stopCompose` | Stopped but retained | Retained | Retained |
| `down` | Removed | Retained | Retained |
| `down --volumes` | Removed | **Deleted** | Retained |

For an ordinary end of the working day, use `stopCompose`/`stop`. Use `down`
only when the containers and Compose network should be recreated. Use
`down --volumes` only for an intentional full dependency and database reset.

## Dev Container And Compose Relationship

A Dev Container is not a special container type and `.devcontainer` is only a
conventional configuration directory. The Dev Containers extension first
finds `.devcontainer/devcontainer.json`, which contains the connection between
VS Code and Compose:

```json
"dockerComposeFile": "compose.yaml",
"service": "workspace"
```

`dockerComposeFile` is resolved relative to `devcontainer.json`, so it selects
`.devcontainer/compose.yaml`. The `service` value tells VS Code which Compose
service is the container that should host the editor, terminals, extensions,
and development processes.

The Compose YAML is not executed inside the workspace container. The Dev
Containers extension invokes Docker Compose through Docker Desktop on the
Windows host. Docker Compose then asks the Docker Engine to create the services
declared in the file:

```text
Compose project: app_devcontainer
        |
        +--> workspace   <- VS Code attaches here; this is the Dev Container
        +--> user-db     <- PostgreSQL sidecar
        +--> todo-db     <- PostgreSQL sidecar
```

Therefore, the complete Compose project is the local development environment,
while only its `workspace` service is used as the Dev Container.

Path values in `compose.yaml` are interpreted relative to the directory that
contains the Compose file. Consequently:

```yaml
build:
  context: .
  dockerfile: Dockerfile
```

selects `.devcontainer/Dockerfile`, while:

```yaml
volumes:
  - ..:/workspace:cached
```

mounts the parent `App` directory from Windows into `/workspace` in the
container.

The extension may generate temporary Compose override files in the host's temp
directory. These add Dev Container Features, identifying labels, the VS Code
server setup, and container lifecycle details on top of the repository's
`compose.yaml`; they do not replace the repository configuration.

## What Runs And When

Several independent VS Code and Docker mechanisms participate in this setup.
They do not execute every repository file whenever **Reopen in Container** is
selected.

### Commands Provided By VS Code

The following commands do not come from this repository:

| Command | Provider | Purpose |
| --- | --- | --- |
| **Dev Containers: Reopen in Container** | VS Code Dev Containers extension | Creates or starts the container environment and attaches VS Code |
| **Tasks: Run Task** | VS Code's built-in Tasks system | Lists tasks discovered in the opened workspace |
| **Terminal: Create New Terminal** | VS Code | Opens an interactive shell in the attached workspace container |

The repository supplies configuration to those systems. It does not implement
the **Reopen in Container** or **Tasks: Run Task** commands themselves.

### First Container Creation Or Rebuild

On the first creation, or after **Dev Containers: Rebuild Container**, this
chain is followed:

```text
Dev Containers extension
        |
        +--> reads .devcontainer/devcontainer.json
        |       |
        |       +--> selects compose.yaml
        |       +--> selects the workspace service
        |       +--> requests Node.js and VS Code extensions
        |       +--> declares forwarded ports
        |       +--> declares postCreateCommand
        |
        +--> Docker Compose reads .devcontainer/compose.yaml
        |       |
        |       +--> builds workspace from .devcontainer/Dockerfile
        |       +--> starts user-db and todo-db
        |       +--> creates/mounts named volumes
        |       +--> bind-mounts App at /workspace
        |
        +--> installs the Node Dev Container Feature into the image
        +--> starts and attaches to the workspace container
        +--> runs .devcontainer/post-create.sh automatically
                |
                +--> creates both Python venvs
                +--> installs Python dependencies and lint tools
                +--> runs npm ci for the frontend
```

At the end of this flow the development environment is prepared, but Uvicorn
and Vite are still not running.

### Normal Reopen Of An Existing Container

When the image and containers already exist, **Reopen in Container** normally
reuses them:

```text
read devcontainer.json
        |
start existing Compose services if stopped
        |
attach VS Code to /workspace
        |
activate port forwarding and container-side extensions
```

In this case the Dockerfile is not rebuilt, the Node Feature is not reinstalled,
and `post-create.sh` does not run again. Named volumes already contain the
installed dependencies and database data.

`post-create.sh` runs again when a new container is created, including after a
Dev Container rebuild. It can also be invoked manually when dependencies need
to be refreshed, but manual execution is not part of every normal start.

### How VS Code Discovers `Dev: Start all`

After VS Code attaches, `/workspace` becomes the opened workspace folder. VS
Code's built-in Tasks system automatically looks for:

```text
/workspace/.vscode/tasks.json
```

That file defines these repository-specific tasks:

| Task label | What it runs |
| --- | --- |
| `Dev: User service` | User Service Uvicorn process with reload on port `8001` |
| `Dev: Todo service` | Todo Service Uvicorn process with reload on port `8002` |
| `Dev: Frontend` | `npm run dev` and the Vite server on port `5173` |
| `Dev: Start all` | The three development tasks above in parallel |
| `Test: Python services` | Both Python test suites |
| `Lint: All` | Black, Flake8, and frontend ESLint |

`Dev: Start all` is therefore not a Dev Container command. It is the `label`
of a composite task in `.vscode/tasks.json`. Selecting **Tasks: Run Task** makes
VS Code read that list; selecting `Dev: Start all` then follows its `dependsOn`
entries and starts the three child tasks.

### Application Startup Chain

The final runtime chain is:

```text
.vscode/tasks.json
        |
        +--> Dev: User service
        |       +--> user-service/.venv/bin/uvicorn
        |               +--> imports user-service/app.py
        |
        +--> Dev: Todo service
        |       +--> todo-service/.venv/bin/uvicorn
        |               +--> imports todo-service/app.py
        |
        +--> Dev: Frontend
                +--> npm run dev
                        +--> reads frontend/package.json script
                        +--> starts Vite
                                +--> reads frontend/vite.config.js
```

Only at this point do ports `5173`, `8001`, and `8002` have listening
application processes. Port forwarding may be configured earlier, but it
returns `ECONNREFUSED` until these processes start.

## File Responsibilities

### `.devcontainer/devcontainer.json`

This is the entry point read by the VS Code Dev Containers extension. It tells
VS Code:

- to use `.devcontainer/compose.yaml`;
- to attach the editor and terminal to the `workspace` service;
- to start the workspace and both database services;
- to use `/workspace` as the opened repository directory;
- to install Node.js `20.20.2` through a Dev Container Feature;
- which VS Code extensions and editor settings belong inside the container;
- which application ports VS Code must forward;
- to run `post-create.sh` after creating the environment.

`shutdownAction: stopCompose` stops the Compose services when the Dev Container
session is closed. It does not delete the named volumes.

### `.devcontainer/compose.yaml`

Compose defines the runtime topology. It creates three long-running containers:

- `workspace`: Python, Node.js, project dependencies, terminals, and all three
  application development processes;
- `user-db`: PostgreSQL for User Service;
- `todo-db`: PostgreSQL for Todo Service.

The workspace command is `sleep infinity`. Its purpose is to keep the
development environment alive so VS Code can attach to it. It is not the
command that starts the application.

`depends_on` waits for both PostgreSQL health checks before the workspace is
started. The service names `user-db` and `todo-db` also become DNS names on the
private Compose network. This is why the backend tasks can use connection
strings such as:

```text
postgresql://userservice:userpass@user-db:5432/userdb
```

The bind mount below makes host edits immediately visible in the container:

```yaml
- ..:/workspace:cached
```

`..` is the `App` directory because `compose.yaml` lives in `.devcontainer`.
`cached` is a Docker Desktop bind-mount consistency/performance hint; it is not
a package cache.

### `.devcontainer/Dockerfile`

The Dockerfile defines the operating-system-level development image. It starts
from the Microsoft Python 3.11 Dev Container image and adds:

- compiler tools required by some Python packages;
- PostgreSQL client headers used by `psycopg2`;
- the `psql` command-line client.

It does not copy application source or install project dependencies. Source is
mounted later by Compose, while project dependencies are installed by
`post-create.sh`. Changing this Dockerfile requires **Dev Containers: Rebuild
Container**.

Node.js is not installed in this Dockerfile. The Node Feature declared in
`devcontainer.json` adds the pinned Node version while VS Code creates the
development image.

### `.devcontainer/post-create.sh`

This lifecycle script prepares repository-level dependencies after the source
and named volumes are mounted. It automatically:

1. creates a separate `.venv` for each Python service;
2. installs each service's `requirements-test.txt` dependencies;
3. installs the Python lint tools used by the repository;
4. runs `npm ci` for the frontend using `package-lock.json`.

The base container is not empty before this script runs: it already contains
Linux, Python, Git, shell tools, PostgreSQL client tools, and the Node Feature.
The script adds only dependencies belonging to this application.

`npm ci` is used for reproducible initial installation. It installs the exact
dependency tree recorded in `package-lock.json`. Normal frontend commands are
still the familiar commands and run from `/workspace/frontend`:

```bash
npm run dev -- --host 0.0.0.0
npm run lint
npm run build
```

### `.vscode/tasks.json`

The tasks file stores repeatable development commands. **Dev: Start all** starts
the following three tasks in parallel:

- **Dev: User service**: Uvicorn on port `8001` with `--reload`;
- **Dev: Todo service**: Uvicorn on port `8002` with `--reload`;
- **Dev: Frontend**: Vite on port `5173` with HMR.

The backend tasks also provide local-only database URLs and other runtime
environment variables. These variables configure the running application;
they are different from dependencies installed by `post-create.sh`.

The file also provides **Test: Python services** and **Lint: All** tasks.

### `frontend/vite.config.js`

The frontend uses relative API paths such as `/login` and `/todos`. In the
Kubernetes environment, Gateway API `HTTPRoute` resources send those paths to
the correct backend service and send `/` to the frontend.

The local Vite server has no Kubernetes Gateway in front of it. Its development
proxy therefore reproduces the same routing locally:

```text
browser -> localhost:5173/login -> Vite proxy -> localhost:8001
browser -> localhost:5173/todos -> Vite proxy -> localhost:8002
```

Before this change, `npm run dev` could still render the frontend, but API calls
using relative paths had no local component that knew which backend should
receive them. They worked in Kubernetes because the `HTTPRoute` performed that
routing.

`server.host: 0.0.0.0` is needed because Vite now runs inside a container.
Binding only to the container's loopback interface would prevent VS Code port
forwarding from reaching it.

The `server` block affects only `npm run dev`. It does not change the production
`npm run build` output or the Caddy container that serves the built frontend.

### `.gitignore` and `.flake8`

`.gitignore` prevents generated virtual environments, Python caches, coverage
data, and test cache files from entering Git. `.flake8` excludes `.venv`
directories so linting checks application code instead of thousands of
installed dependency files.

## Storage And Caches

The source code and generated dependencies use different storage types:

| Data | Storage | Purpose |
| --- | --- | --- |
| Repository source | Windows directory bind-mounted at `/workspace` | Host and container see the same edits immediately |
| `user-service/.venv` | Docker named volume | Installed User Service Python packages |
| `todo-service/.venv` | Docker named volume | Installed Todo Service Python packages |
| `frontend/node_modules` | Docker named volume | Installed frontend packages |
| pip cache | Docker named volume | Downloaded Python wheels and archives reused by pip |
| npm cache | Docker named volume | Downloaded npm package data reused by npm |
| PostgreSQL data | Two Docker named volumes | Local development databases survive container restarts |

The pip cache and each `.venv` solve different problems. The cache avoids
downloading a package again; the venv contains the installed, executable copy
used by the service. The same distinction applies to npm cache and
`node_modules`.

These named volumes are managed inside Docker Desktop's Linux storage, not as
ordinary directories beside the source repository. They can be inspected with:

```bash
docker volume ls
docker volume inspect app_devcontainer_user-service-venv
```

The exact Compose-generated prefix can vary with the project directory name.

### Why Two Python Virtual Environments?

A container isolates the development environment from Windows, but it does not
automatically isolate Python packages from each other inside that container. A
Dev Container is therefore not a Python virtual environment.

Separate venvs keep User Service and Todo Service dependencies independent. The
services happen to share several versions now, but either service can change
later without modifying the other's environment. This also matches the CI
model and makes moving each service to its own repository less disruptive.

## Source Reload Behavior

No image rebuild is needed for normal application edits:

- a Python file saved on Windows changes the bind-mounted file in `/workspace`;
- Uvicorn `--reload` restarts the relevant Python process;
- Vite HMR applies frontend changes in the browser;
- database files remain in their named volumes.

Use the following rule of thumb:

| Change | Required action |
| --- | --- |
| Python, JSX, CSS, or other source | Save the file; reload/HMR handles it |
| `requirements-test.txt` | Rerun `bash .devcontainer/post-create.sh` or install into the relevant venv |
| `package-lock.json` | Run `npm --prefix frontend ci` |
| Dockerfile, Node Feature, Compose, or Dev Container configuration | Run **Dev Containers: Rebuild Container** |

## Direct Commands

The VS Code tasks are shortcuts, not a new application runtime. The same
commands can be run directly in the Dev Container terminal.

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

Tests and lint checks can also be run directly:

```bash
user-service/.venv/bin/pytest user-service
todo-service/.venv/bin/pytest todo-service
user-service/.venv/bin/black --check --diff user-service todo-service
user-service/.venv/bin/flake8 user-service todo-service
npm --prefix frontend run lint
```

## Resetting The Environment

**Dev Containers: Rebuild Container** recreates the workspace container but
keeps named volumes. Use it when the development image or Dev Container
configuration changes.

Deleting the Compose volumes is a stronger reset. It removes installed
dependencies and both local databases, so the next creation installs packages
again and starts with empty databases:

```bash
docker compose \
  --project-name app_devcontainer \
  -f .devcontainer/compose.yaml \
  down --volumes
```

Run that command only when the local development data is intentionally
disposable. The credentials in `compose.yaml` are local-development values and
must not be reused in staging or production.
