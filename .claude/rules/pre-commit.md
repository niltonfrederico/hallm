---
description: Enforces pre-commit hook pinning whenever .pre-commit-config.yaml is modified.
globs: ".pre-commit-config.yaml"
alwaysApply: false
---

# Pre-commit Hook Pinning

Whenever you modify `.pre-commit-config.yaml`, run:

```bash
pre-commit autoupdate
```

This pins every hook to its latest release tag. Do this before committing the config change.
