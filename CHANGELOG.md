# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- Added `shipyard update-docs` command (CI only): runs a documentation agent over the cumulative epic diff, commits the result, then iterates with a verifier sub-agent until it outputs LGTM.
- Added `update-docs` job to `epic-driver.yml`: triggers when the last PR in an epic is merged and no remaining work exists, then runs `shipyard update-docs` and pushes documentation changes.
- Added `doc_agent.md` and `doc-verifier.md` prompts for the documentation agent and its verifier sub-agent.
- Added `SHIPYARD_DOC_MODEL`, `SHIPYARD_DOC_EFFORT`, `SHIPYARD_DOC_REVIEW_MODEL`, and `SHIPYARD_DOC_REVIEW_EFFORT` settings to control the documentation agent's model and effort level.
- Added `plan-driver.yml` workflow: triggers on `plan` label or `CHANGES_REQUESTED` review, runs a planning agent to produce or revise `plans/i<N>.md`, and opens a draft PR.
- Added `sync-driver.yml` workflow: triggers on merged plan PRs, converts the plan file into GitHub Issues automatically.
- `shipyard init` now installs all three workflows (`epic-driver.yml`, `plan-driver.yml`, `sync-driver.yml`) by default; use `--skip-plan-driver` to install only `epic-driver.yml`.
- `shipyard sync` now creates and pushes the `shipyard/epic-<N>` branch at the end of the sync run.
- `shipyard publish-execution` gained a `--base-branch` flag to override the PR target branch (default: `SHIPYARD_PR_BASE_BRANCH`, fallback `main`).

### Changed

- Improved planning agent prompts: better issue context, clearer re-plan instructions.
- Improved PR creation: the PR body now links to the originating issue.
- `epic-driver.yml`: added `issues: write` permission required for posting failure comments.

### Fixed

- Fixed incorrect string concatenation for task context in `shipyard execute`.
