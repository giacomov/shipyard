#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

bash "$DIR/test-epic-driver.sh" "$@"
bash "$DIR/test-plan-driver.sh" "$@"
bash "$DIR/test-sync-driver.sh" "$@"
