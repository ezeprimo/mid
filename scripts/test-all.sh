#!/usr/bin/env bash
# Run all project tests: Python (pytest)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PASS=0
FAIL=0

run_test_suite() {
    local name="$1"
    local cmd="$2"
    echo ""
    echo "========================================"
    echo "  $name"
    echo "========================================"
    if eval "$cmd"; then
        echo "  PASS  $name"
        PASS=$((PASS + 1))
    else
        echo "  FAIL  $name"
        FAIL=$((FAIL + 1))
    fi
}

run_test_suite "Python tests (pytest)"  "python -m pytest -v"
echo ""
echo "=============================="
echo "  Suites: $PASS passed, $FAIL failed"
echo "=============================="

[[ "$FAIL" -eq 0 ]] && exit 0 || exit 1
