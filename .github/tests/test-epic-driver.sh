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

# Case 1: issues.labeled with 'in-progress' label (triggers find-work + execute)
run gh act issues \
  -e .github/tests/events/epic-issues-labeled.json \
  -W .github/workflows/epic-driver.yml \
  $EXTRA_FLAGS

# Case 2: pull_request.closed (merged implementation PR — triggers find-work for next task,
#          or update-docs if no work remains)
run gh act pull_request \
  -e .github/tests/events/epic-pr-merged.json \
  -W .github/workflows/epic-driver.yml \
  $EXTRA_FLAGS

# Case 3: workflow_dispatch with explicit issue_number input
run gh act workflow_dispatch \
  --input issue_number=42 \
  -W .github/workflows/epic-driver.yml \
  $EXTRA_FLAGS
