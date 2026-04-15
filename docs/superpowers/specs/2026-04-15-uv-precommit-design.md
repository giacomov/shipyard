---
title: uv dependency management + ruff pre-commit
date: 2026-04-15
status: approved
---

# uv Dependency Management + ruff Pre-commit

## Goal

Replace the ad-hoc dependency setup (loose `>=` bounds, legacy `requirements.txt`) with a uv-managed workflow that provides deterministic developer environments and supply-chain-safe end-user installs. Add a ruff pre-commit hook for consistent linting and formatting.

---

## 1. Dependency management

### pyproject.toml changes

- `requires-python` updated to `">=3.13"`.
- Runtime deps (`claude-agent-sdk`, `click`) pinned exactly with `==` so that `uv tool install git+https://...@<tag>` installs a fully deterministic, no-surprise-upgrades set of packages for end users.
- Dev deps (`pytest`, `pytest-asyncio`, `pre-commit`) moved from `[project.optional-dependencies]` to `[dependency-groups]` (uv-native, PEP 735). Dev deps are also exact-pinned. They are never installed by `uv tool install`.
- `requirements.txt` is deleted.

### Pinned versions

| Package | Pin | Group |
|---------|-----|-------|
| `claude-agent-sdk` | `==0.1.59` | runtime |
| `click` | `==8.2.1` | runtime |
| `pytest` | `==9.0.3` | dev |
| `pytest-asyncio` | `==1.3.0` | dev |
| `pyyaml` | `==6.0.2` | dev |
| `pre-commit` | `==4.5.1` | dev |

### uv.lock

`uv.lock` is committed to the repository and is the authoritative snapshot for the developer environment. It is generated and updated exclusively via `uv` commands — never edited by hand.

### Install paths

- **End users:** `uv tool install git+https://github.com/owner/shipyard@v<tag>` — gets exact-pinned runtime deps, no dev deps.
- **Contributors:** `uv sync` — installs all deps (runtime + dev) from `uv.lock`.

### CLAUDE.md rules (to be added)

- Never edit dependency versions in `pyproject.toml` by hand.
- To add or update a runtime dep: `uv add 'pkg==x.y.z'`
- To add or update a dev dep: `uv add --dev 'pkg==x.y.z'`
- Always commit `pyproject.toml` and `uv.lock` together in the same commit.
- `uv.lock` and the pinned versions in `pyproject.toml` must stay in sync — the lock file is generated from `pyproject.toml`, so running `uv lock` after any change to deps is sufficient to keep them aligned.

---

## 2. ruff pre-commit hook

### .pre-commit-config.yaml

Single hook source: `astral-sh/ruff-pre-commit` at the latest release tag (`v0.15.10`).

Two hooks, in order:
1. `ruff` — lint with `--fix` (auto-fixes safe issues)
2. `ruff-format` — format (black-compatible)

Both run on staged Python files only.

### pyproject.toml ruff config

```toml
[tool.ruff]
target-version = "py313"
line-length = 88

[tool.ruff.lint]
select = ["E", "F", "I"]
```

- `E` — pycodestyle errors
- `F` — pyflakes (undefined names, unused imports)
- `I` — isort (import ordering)

### Contributor setup

After cloning, contributors run:

```bash
uv sync
uv run pre-commit install
```

This is added to the CLAUDE.md setup instructions, replacing the current `pip install -e ".[dev]"`.

---

## 3. Files changed

| File | Change |
|------|--------|
| `pyproject.toml` | Update `requires-python`, exact pins, move dev deps to `[dependency-groups]`, add `[tool.ruff]` |
| `uv.lock` | Generated fresh via `uv lock` |
| `.pre-commit-config.yaml` | New file |
| `requirements.txt` | Deleted |
| `CLAUDE.md` | Update setup commands and add dep-management rules |
