# Agent Pipeline

`shipyard execute` drives a three-agent pipeline for every unblocked GitHub Issue passed to it via `$WORK_JSON`.

## What `shipyard execute` Does

1. Reads `$WORK_JSON` (produced by `shipyard find-work`) and deserializes it into a `SubtaskList`.
2. Iterates over each task **sequentially** (one at a time).
3. For each task, records the current `HEAD` SHA as `base_sha`, then runs the three-agent pipeline.
4. Writes `shipyard-results.json` with `{ "successful": [...], "failed": [...] }` task ID lists.

Branch creation, push, and PR opening are handled separately by `shipyard publish-execution` (the next step in the workflow), which reads `shipyard-results.json`.

## The Three-Agent Sequence

```
┌──────────────────────────────────────────────┐
│  For each issue                               │
│                                               │
│  attempt = 0 .. max_retries (default: 1)      │
│                                               │
│  ┌─────────────────────────┐                  │
│  │  Implementer agent       │                  │
│  │  prompt: implementer.md  │                  │
│  │  tools: Bash,Read,Write, │                  │
│  │         Edit,Glob,Grep   │                  │
│  └──────────┬──────────────┘                  │
│             │ implementer_report               │
│             ▼                                 │
│  ┌─────────────────────────┐                  │
│  │  Spec Reviewer agent     │                  │
│  │  prompt: spec-reviewer   │                  │
│  └──────────┬──────────────┘                  │
│             │ verdict: APPROVED / CHANGES      │
│             ▼                                 │
│  ┌─────────────────────────┐                  │
│  │  Code Quality Reviewer   │                  │
│  │  prompt: code-quality    │                  │
│  └──────────┬──────────────┘                  │
│             │ verdict: APPROVED / CHANGES      │
│             ▼                                 │
│     both approved? ──yes──► next issue        │
│          │ no                                 │
│          └── attempt < max_retries?           │
│               yes ──► reset + retry           │
│               no  ──► post failure comment    │
└──────────────────────────────────────────────┘
```

### Agent 1: Implementer

- Receives the issue body as `{TASK_DESCRIPTION}` and a context block as `{CONTEXT}`.
- Context includes: repo name, epic number/title, epic body, and (on retries) the previous reviewer feedback.
- Has full filesystem tools: `Bash`, `Read`, `Write`, `Edit`, `Glob`, `Grep`.
- Runs in `bypassPermissions` mode (CI environment, no human approvals).
- Must follow TDD: write failing test → implement → verify passing → commit.
- Ends its report with a status line.

### Agent 2: Spec Reviewer

- Receives the original `{TASK_DESCRIPTION}` and `{IMPLEMENTER_REPORT}`.
- **Does not trust the implementer's report**; must read actual code via `git diff {BASE_SHA}..HEAD`.
- Checks for missing requirements, over-engineering, and misunderstandings.
- Outputs `APPROVED` or `CHANGES_REQUESTED` with file:line references.

### Agent 3: Code Quality Reviewer

- Runs only after the spec reviewer approves.
- Reads `{IMPLEMENTER_REPORT}` and the git diff for the same range.
- Reviews type hints, error handling, test quality, architecture, and security.
- Outputs `APPROVED` or `CHANGES_REQUESTED` with a structured report.

## Retry Logic

- Default `max_retries = 1` (meaning up to 2 total attempts per issue).
- If the spec reviewer requests changes and attempts remain, the implementer's report is replaced with `"Spec review feedback:\n{spec_output}"` and `git reset --hard base_sha` is called before the next attempt.
- If the code quality reviewer requests changes and attempts remain, the implementer's report is replaced with `"Code quality review feedback:\n{quality_output}"` and the same reset is applied.
- Both reviewers must approve within the same attempt for the issue to succeed.

## Implementer Status

The implementer agent communicates its outcome through the ClaudeSDKClient session. The pipeline delegates review and retry decisions to the agent itself — the spec reviewer and code quality reviewer run as sub-agents within the same session, and the implementer is instructed to fix issues and re-run reviewers until they pass.

## Failure Handling

When an issue fails (any terminal condition):

1. `git reset --hard base_sha` — all uncommitted and committed changes for that issue are discarded.
2. A comment is posted on the GitHub Issue with:
   - An HTML comment tag: `<!-- shipyard-executor: <REASON> -->`
   - A human-readable summary.
   - A collapsible `<details>` section containing the relevant agent output.
3. Execution continues with the next issue.

The overall `shipyard execute` process exits with code 1 if any issues failed.

## Success Handling

When both reviews approve an issue:

- The commits are left on the branch (no special action needed).
- The task ID is added to the `successful` list in `shipyard-results.json`.

After all tasks are processed, `shipyard publish-execution` (the next workflow step) reads `shipyard-results.json` and:

1. `git push -u origin <branch>` pushes all accumulated commits.
2. `gh pr create` opens a PR with:
   - Title: `shipyard: implement N task(s) from epic #<epic_id>`
   - Body: an intro line ("This PR implements the following issues:") followed by `Closes #<n>` lines for every successful task (using task ID as issue number).
   - Base branch: `main` (configurable via `SHIPYARD_PR_BASE_BRANCH`).

If no issues succeeded, `shipyard publish-execution` skips push and PR creation entirely.
