# Copilot Instructions — hallm

See `.claude/CLAUDE.md` for the full project reference (tech stack, conventions, file layout, database schema, and common commands).

## Pre-commit hooks

Whenever you modify `.pre-commit-config.yaml`, run:

```bash
pre-commit autoupdate
```

This pins every hook to its latest release tag. Do this before committing the config change.

## QA requirement

**After completing every request**, run the `qa` skill (or `/qa` prompt) to execute the full quality gate. Steps are defined in `.github/skills/qa/SKILL.md`.
