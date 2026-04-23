# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- Added `plan-driver.yml` workflow: triggers on `plan` label or `CHANGES_REQUESTED` review, runs a planning agent to produce or revise `plans/i<N>.md`, and opens a draft PR.
- Added `sync-driver.yml` workflow: triggers on merged plan PRs, converts the plan file into GitHub Issues automatically.
- Added `doc_agent.md` prompt for the documentation agent.
- `shipyard init` now installs all three workflows (`epic-driver.yml`, `plan-driver.yml`, `sync-driver.yml`) by default; use `--skip-plan-driver` to install only `epic-driver.yml`.

### Changed

- Improved planning agent prompts: better issue context, clearer re-plan instructions.
- Improved PR creation: the PR body now links to the originating issue.
- `epic-driver.yml`: added `issues: write` permission required for posting failure comments.
