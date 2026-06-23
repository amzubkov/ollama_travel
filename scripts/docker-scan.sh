#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
mkdir -p logs

exec timeout --kill-after=30s 20m docker compose run --rm agent scan
