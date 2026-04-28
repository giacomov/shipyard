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

# Case 1: issues.labeled with 'plan' label (generate a new plan)
run gh act issues \
  -e .github/tests/events/plan-issues-labeled.json \
  -W .github/workflows/plan-driver.yml \
  $EXTRA_FLAGS

# Case 2: pull_request_review.submitted with CHANGES_REQUESTED (revise plan or address feedback)
run gh act pull_request_review \
  -e .github/tests/events/plan-review-changes-requested.json \
  -W .github/workflows/plan-driver.yml \
  $EXTRA_FLAGS
