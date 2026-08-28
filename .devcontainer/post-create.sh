#!/usr/bin/env bash

set -euo pipefail

readonly WORKSPACE_DIR="/workspace"
readonly PYTHON_LINT_PACKAGES=(
  "black==25.9.0"
  "flake8==7.3.0"
  "ruff==0.9.3"
)

prepare_python_service() {
  local service_name="$1"
  local service_dir="${WORKSPACE_DIR}/${service_name}"
  local venv_dir="${service_dir}/.venv"

  sudo chown -R vscode:vscode "$venv_dir"
  python -m venv "$venv_dir"
  "$venv_dir/bin/python" -m pip install --upgrade pip setuptools wheel
  "$venv_dir/bin/python" -m pip install \
    "${PYTHON_LINT_PACKAGES[@]}" \
    -r "${service_dir}/requirements-test.txt"
}

sudo chown -R vscode:vscode \
  /home/vscode/.cache/pip \
  /home/vscode/.npm \
  "${WORKSPACE_DIR}/frontend/node_modules"

prepare_python_service "user-service"
prepare_python_service "todo-service"

npm --prefix "${WORKSPACE_DIR}/frontend" ci --no-audit --no-fund

echo "Development dependencies are ready. Run the 'Dev: Start all' VS Code task."
