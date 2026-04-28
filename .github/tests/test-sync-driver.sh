#!/usr/bin/env bash
set -euo pipefail

EXTRA_FLAGS=""

for arg in "$@"; do
  case "$arg" in
    --dry-run|-n) EXTRA_FLAGS="-n" ;;
  esac
done

run() {
  echo ">>> $*"
  "$@"
  echo
}

# Case 1: pull_request.closed (merged plan PR with 'plan' label — syncs tasks to GitHub Issues)
run gh act pull_request \
  -e .github/tests/events/sync-pr-merged-plan.json \
  -W .github/workflows/sync-driver.yml \
  $EXTRA_FLAGS
