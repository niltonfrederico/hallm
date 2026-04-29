Run the full QA suite: lint (with auto-fix retry) then tests.

## Steps

1. Run `docker compose down --remove-orphans` to clean up any leftover containers.
2. Run `docker compose run --rm lint` and capture the exit code.
2. If it exited non-zero (lint applied fixes or found errors), run it **once more** to determine whether the remaining issues are real errors or just auto-fix noise.
   - If the second run also exits non-zero, report the lint errors to the user and **stop** — do not proceed to tests.
   - If the second run exits zero, continue.
3. Run `docker compose run --rm tests`.
4. Report a clear summary: lint status (clean / fixed / failed) and test status (passed / failed), including any relevant output for failures.
