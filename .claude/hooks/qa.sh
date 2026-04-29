#!/usr/bin/env bash
set -euo pipefail

docker compose down --remove-orphans 2>/dev/null || true

docker compose --profile lint run --rm lint
LINT1=$?

if [ $LINT1 -ne 0 ]; then
    echo "Lint applied fixes — re-running to check for remaining errors..."
    docker compose --profile lint run --rm lint
    LINT2=$?
    if [ $LINT2 -ne 0 ]; then
        echo "Lint failed after auto-fix pass. Fix the errors above before proceeding."
        exit 1
    fi
fi

docker compose --profile test run --rm tests
