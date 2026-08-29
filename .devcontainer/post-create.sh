#!/usr/bin/env bash

set -euo pipefail

readonly WORKSPACE_DIR="/workspace"

prepare_python_service() {
  local service_name="$1"
  local service_dir="${WORKSPACE_DIR}/${service_name}"
  local venv_dir="${service_dir}/.venv"

  sudo chown -R vscode:vscode "$venv_dir"
  uv sync --project "$service_dir" --locked
}

sudo chown -R vscode:vscode \
  /home/vscode/.cache/uv \
  /home/vscode/.npm \
  "${WORKSPACE_DIR}/frontend/node_modules"

prepare_python_service "user-service"
prepare_python_service "todo-service"

npm --prefix "${WORKSPACE_DIR}/frontend" ci --no-audit --no-fund

echo "Development dependencies are ready. Run the 'Dev: Start all' VS Code task."
