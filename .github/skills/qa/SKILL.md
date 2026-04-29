---
name: qa
description: 'Run the full QA suite for hallm: lint (with auto-fix retry) then tests via Docker Compose. Use after completing any coding task, when asked to run QA, or to verify code quality before committing.'
---

# QA Suite

Runs the project lint and test pipeline via Docker Compose.

## When to Use

- After completing any coding request
- When asked to verify code quality or run QA
- Before committing changes

## Procedure

1. Run `docker compose down --remove-orphans` to clean up any leftover containers.
2. Run `docker compose --profile lint run --rm lint` and capture the exit code.
3. If it exited non-zero (lint applied fixes or found errors), run it **once more**:
   - If the second run also exits non-zero: report the lint errors and **stop** — do not proceed to tests.
   - If the second run exits zero: continue.
4. Run `docker compose --profile test run --rm tests`.
5. Report a clear summary: lint status (clean / fixed / failed) and test status (passed / failed), including any relevant output for failures.
