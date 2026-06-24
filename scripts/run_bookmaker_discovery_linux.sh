#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${SUREBET_PROJECT_DIR:-/opt/surebet}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
LOG_DIR="${PROJECT_DIR}/outputs/bookmaker_discovery/logs"
LOG_FILE="${LOG_DIR}/bookmaker_discovery.log"

mkdir -p "${LOG_DIR}"
cd "${PROJECT_DIR}"

exec "${PYTHON_BIN}" main.py --mode bookmaker-discovery >> "${LOG_FILE}" 2>&1
