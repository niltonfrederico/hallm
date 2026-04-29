# Copilot Instructions — hallm

See `.claude/CLAUDE.md` for the full project reference (tech stack, conventions, file layout, database schema, and common commands).

## QA requirement

**After completing every request**, run `/qa` to execute the full quality gate:

1. `docker compose down --remove-orphans`
2. `docker compose --profile lint run --rm lint` — if it exits non-zero (auto-fixes applied), run it once more; stop and report if it still fails.
3. `docker compose --profile test run --rm tests` — only if lint passed.

Report a clear summary: lint status (clean / fixed / failed) and test status (passed / failed).
