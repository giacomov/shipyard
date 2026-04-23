# Agent pipeline

`shipyard execute` drives a three-agent pipeline for every unblocked GitHub Issue passed to it via a work JSON file.

## What `shipyard execute` does

1. Reads the work JSON file (produced by `shipyard find-work`, passed via `-i`) and deserializes it into a `SubtaskList`.
2. Iterates over each task **sequentially** (one at a time).
3. For each task, records the current `HEAD` SHA as `base_sha`, then runs the three-agent pipeline.
4. Writes `shipyard-results.json` with `{ "successful": [...], "failed": [...] }` task ID lists.

Branch creation, push, and PR opening are handled separately by `shipyard publish-execution` (the next step in the workflow), which reads `shipyard-results.json`.

## The three-agent sequence

The implementer, spec reviewer, and code quality reviewer share a single `ClaudeSDKClient` session. The spec reviewer and code quality reviewer are registered as named sub-agents (`AgentDefinition`) that the implementer can invoke via the `Agent` tool.

```
┌──────────────────────────────────────────────────┐
│  For each issue                                   │
│                                                   │
│  ┌─────────────────────────────────┐              │
│  │  Implementer (main agent)        │              │
│  │  tools: Bash,Read,Write,Edit,    │              │
│  │         Glob,Grep,Agent,Monitor  │              │
│  │                                 │              │
│  │  1. Implement the task          │              │
│  │  2. Stage and commit changes    │              │
│  │  3. Invoke spec_reviewer ◄──────┤ sub-agent    │
│  │     (fix & retry if needed)     │              │
│  │  4. Invoke code_quality_reviewer◄┤ sub-agent    │
│  │     (fix & retry if needed)     │              │
│  │  5. Run tests until they pass   │              │
│  └────────────────────────────────┘              │
│                                                   │
│  Pipeline exception? ──► reset + failure comment  │
└──────────────────────────────────────────────────┘
```

### Implementer (main agent)

- Receives the issue body as `{TASK_DESCRIPTION}` and a context block as `{CONTEXT}`.
- Context includes: epic title and list of all tasks in the plan, with the current task marked `[current task]`.
- Has tools: `Bash`, `Read`, `Write`, `Edit`, `Glob`, `Grep`, `Agent`, `Monitor`.
- Runs in `dontAsk` permission mode (CI environment, no human approvals).
- Follows TDD: write failing test → implement → verify passing → commit.
- After committing, the pipeline sends follow-up `query()` calls instructing the implementer to invoke the spec reviewer and code quality reviewer sub-agents, iterating until both pass.

### Spec reviewer (sub-agent)

- Registered as `spec_reviewer` in `ClaudeAgentOptions.agents`.
- Receives `{TASK_DESCRIPTION}`, `{CONTEXT}`, and `{BASE_SHA}`.
- Runs `git diff {BASE_SHA}..HEAD` to identify what changed — reviews only the diff, not pre-existing code.
- Checks for missing requirements, over-engineering, and misunderstandings.
- Tools: `Bash`, `Read`, `Grep`, `Glob`.

### Code quality reviewer (sub-agent)

- Registered as `code_quality_reviewer` in `ClaudeAgentOptions.agents`.
- Invoked by the implementer after the spec reviewer passes.
- Receives `{TASK_DESCRIPTION}`, `{CONTEXT}`, and `{BASE_SHA}`.
- Runs `git diff --stat {BASE_SHA}..HEAD` and `git diff {BASE_SHA}..HEAD` — reviews only the diff.
- Reviews type hints, error handling, test quality, architecture, and security.
- Tools: `Bash`, `Read`, `Grep`, `Glob`.

## Retry logic

The implementer is instructed to fix issues raised by either reviewer and re-invoke that reviewer until it passes. This happens within a single session — there is no external reset-and-retry loop at the pipeline level.

## Failure handling

When an issue fails (any terminal condition):

1. `git reset --hard base_sha` — all uncommitted and committed changes for that issue are discarded.
2. A comment is posted on the GitHub Issue with:
   - An HTML comment tag: `<!-- shipyard-executor: <REASON> -->`
   - A human-readable summary.
   - A collapsible `<details>` section containing the relevant agent output.
3. Execution continues with the next issue.

The overall `shipyard execute` process exits with code 1 if any issues failed.

## Success handling

When both reviews approve an issue:

- The commits are left on the branch (no special action needed).
- The task ID is added to the `successful` list in `shipyard-results.json`.

After all tasks are processed, `shipyard publish-execution` (the next workflow step) reads `shipyard-results.json` and:

1. `git push -u origin <branch>` pushes all accumulated commits.
2. `gh pr create` opens a PR with:
   - Title: `shipyard: implement N task(s) from epic #<epic_id>`
   - Body: an intro line ("This PR implements the following issues:") followed by `Closes #<n>` lines for every successful task (using task ID as issue number).
   - Base branch: the epic branch (`shipyard/epic-<N>`), as passed by the workflow via `--base-branch`.

If no issues succeeded, `shipyard publish-execution` skips push and PR creation entirely.
