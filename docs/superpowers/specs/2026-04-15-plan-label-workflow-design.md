# Plan Label Workflow Feature Design

**Date:** 2026-04-15  
**Status:** Design Complete  
**Author:** Brainstorming Process

---

## Overview

When a user labels an issue as "plan", an AI agent automatically creates a branch, generates a structured implementation plan, and opens a PR. The user can iterate on the plan via PR reviews with "Request Changes" status, triggering re-planning runs. When the PR is merged, the original issue is closed.

---

## Feature Flow

```
Issue #42 labeled "plan"
         ↓
   plan-driver.yml / plan job
         ↓
   shipyard extract-github-event (creates prompt.txt)
         ↓
   shipyard plan (reads prompt, runs Plan subagent via Agent SDK)
         ↓
   plans/i42.md created + committed to branch plan/i42
         ↓
   PR opened: "Plan: <issue title>" (draft, body contains "Closes #42")
         ↓
   User reviews → submits REQUEST_CHANGES → replan job triggers
         ↓
   shipyard extract-github-event (creates prompt.txt + review-feedback.txt)
         ↓
   shipyard plan (reads prompt + feedback + existing plan, runs Plan subagent)
         ↓
   plans/i42.md updated + committed to same branch plan/i42
         ↓
   User reviews → APPROVES + MERGES → original issue #42 closed
```

---

## Architecture

### New Components

#### 1. `shipyard plan` Command

**Location:** `shipyard/commands/plan.py`

**Signature:**
```bash
shipyard plan \
  (--prompt <text> | --prompt-file <path>) \
  [--issue-number <N>] \
  [--pr-number <N>] \
  [--existing-plan-path <path>] \
  [--review-feedback-file <path>] \
  [--branch-name <name>]
```

**Required parameters:**
- `--prompt` or `--prompt-file`: The planning context (issue title, body, conversation history)

**Optional parameters (with sensible defaults):**
- `--issue-number` (default: `"local-test"`) - Used for branch/file naming and issue link
- `--pr-number` (default: `None`) - Indicates a re-planning run
- `--existing-plan-path` (default: `None`) - Loads previous plan for re-planning context
- `--review-feedback-file` (default: `None`) - File containing review feedback
- `--branch-name` (default: auto-generated) - Override branch name if needed

**Responsibilities (Initial Run):**
1. Read prompt from file or inline argument
2. Invoke Claude Agent SDK's Plan subagent with prompt context
3. Extract plan markdown from agent output
4. Add issue link reference at top of plan file
5. Create branch `plan/i<ISSUE_NUMBER>` from current HEAD
6. Write plan to `plans/i<ISSUE_NUMBER>.md`
7. Commit: `"docs: add implementation plan for issue #<N>"`
8. Push branch to origin
9. Create PR with title `"Plan: <issue title>"`, body includes `"Closes #<ISSUE_NUMBER>"`

**Responsibilities (Re-planning Run):**
1. Read prompt from file
2. Read existing plan file
3. Read review feedback file
4. Invoke Plan subagent with context: "Previous plan + feedback"
5. Extract revised plan markdown
6. Commit to `plans/i<ISSUE_NUMBER>.md`
7. Push to same branch (PR auto-updates)

#### 2. `extract-github-event` Utility Module

**Location:** `shipyard/utils/github_event.py`

**Responsibilities:**
- Parse `GITHUB_EVENT_PATH` JSON based on event type
- For `issues` labeled event: Extract issue #, title, body
- For `pull_request_review` REQUEST_CHANGES event: Extract PR #, review body, linked issue
- Fetch full issue context via `gh` CLI if needed
- Output environment variables for workflow steps to consume

**Functions:**
- `parse_github_event(event_json: dict) -> tuple[int, str]` - Returns (issue_number, repo)
- `fetch_issue_context(repo: str, issue_number: int) -> dict` - Returns {issue_number, issue_title, issue_body, repo}
- `extract_issue_from_pr_review(event_json: dict, repo: str) -> int` - Extracts issue from PR closing references

#### 3. `plan-driver.yml` Workflow Template

**Location:** `shipyard/templates/plan-driver.yml`

**Triggers:**
```yaml
on:
  issues:
    types: [labeled]
  pull_request_review:
    types: [submitted]
```

**Job 1: `plan` (runs when "plan" label added OR REQUEST_CHANGES submitted)**

Conditions:
- `github.event_name == 'issues' && github.event.label.name == 'plan'` (initial plan)
- `github.event_name == 'pull_request_review' && github.event.review.state == 'REQUEST_CHANGES'` (re-plan)

Steps:
1. `actions/checkout@v4` (check out repo)
2. `astral-sh/setup-uv@v4` (install uv + Python)
3. `uv tool install "git+https://github.com/giacomov/shipyard@vSHIPYARD_VERSION"`
4. `shipyard extract-github-event` (parses event JSON, creates prompt.txt, review-feedback.txt if needed)
5. Configure git identity (github-actions[bot])
6. `shipyard plan --prompt-file prompt.txt --issue-number <N> [--review-feedback-file review-feedback.txt]`
7. Commit & push updated plan

**Permissions:** `contents: write`, `pull-requests: write`, `issues: read`, `id-token: write`

**SHIPYARD_VERSION Placeholder:** Substituted by `shipyard init` command (like epic-driver.yml)

#### 4. Plan File Format

**Location:** `plans/i<ISSUE_NUMBER>.md`

**Structure:**
```markdown
<!-- Related to: #<ISSUE_NUMBER> https://github.com/<REPO>/issues/<ISSUE_NUMBER> -->

# <Plan Title>

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans

**Goal:** [One sentence]

**Architecture:** [2-3 sentences]

**Tech Stack:** [Key technologies]

---

### Task 1: [Component Name]

**Depends on:** (none)

...
```

The plan file follows the format specified in `prompts/planner.md`, with an HTML comment linking back to the original issue at the top.

---

## Technology Choices

### Plan Generation: Claude Agent SDK

- Use the built-in Plan subagent from `claude_agent_sdk.query()`
- No custom `planner-agent.md` prompt needed; the Plan subagent handles planning autonomously
- Pass issue context (title + body + conversation) as the prompt
- The agent outputs markdown that follows `prompts/planner.md` format

### GitHub Interactions: `gh` CLI

- All GitHub API calls go through `gh` CLI subprocess (consistent with `sync.py`, `execute.py`, `find_work.py`)
- No direct GitHub API client library

### Installation: `uv tool install`

- Consistent with `epic-driver.yml`
- SHIPYARD_VERSION placeholder substitution in workflow template

### Testing

- Unit tests with mocked subprocess, gh CLI, Agent SDK
- Integration tests with real file I/O, mocked Agent SDK
- Validation tests for YAML syntax and plan format
- Manual testing with actual GitHub repo before merge

---

## Integration with Existing Workflows

### Relationship to `epic-driver.yml`

- **Plan workflow:** Generates structured plans from issues
- **Epic workflow:** Executes tasks within an approved plan (epic issue + sub-issues + agent pipeline)

Both workflows can coexist. A user may:
1. Label issue → generates plan PR → iterates → merges → closes issue
2. Later use `shipyard sync` to turn approved plan into Epic + tasks, which triggers epic-driver workflow

### Update to `shipyard init`

- Extend `init.py` to copy both `epic-driver.yml` and `plan-driver.yml` templates
- Add `--skip-plan-driver` flag (optional; default is to install both)
- Substitute `SHIPYARD_VERSION` in both workflow files

---

## Error Handling

| Error | Handling |
|-------|----------|
| Missing issue context | Fail with error message, post comment on issue |
| Agent SDK timeout/failure | Fail job, post comment on issue with error |
| git operations fail (branch, push) | Reset to base SHA, fail job with error |
| gh CLI calls fail (PR creation) | Retry once, then fail job |
| Malformed GitHub event JSON | Fail with clear error message |

---

## Testing Strategy

### Unit Tests
- Test plan command option parsing
- Test GitHub event parsing (issues, pull_request_review)
- Test git operations (branch, commit, push) with mocked subprocess
- Test PR creation with mocked gh CLI
- Test plan file format validation

### Integration Tests
- End-to-end plan generation (mocked Agent SDK, real file I/O)
- Verify plan file created with correct format and location
- Verify PR created with correct title/body
- Verify REQUEST_CHANGES triggers regeneration with feedback

### Validation Tests
- Validate plan-driver.yml YAML syntax
- Validate plan markdown follows `prompts/planner.md` format
- Test all Click command options

### Manual Testing
- Create test issue in test repo
- Label "plan" → verify workflow runs
- Submit REQUEST_CHANGES review → verify plan regenerates
- Merge PR → verify original issue closes

---

## Implementation Tasks (10 Tasks)

See the detailed execution plan from the Plan subagent for step-by-step tasks:

1. **Create `shipyard plan` command structure**
2. **Create `extract-github-event` utility module**
3. **Implement plan generation with Agent SDK**
4. **Implement git operations (branch, commit, push)**
5. **Implement PR creation and management**
6. **Create `plan-driver.yml` workflow template**
7. **Update `shipyard init` to install both workflows**
8. **Add comprehensive tests**
9. **Document plan feature in `docs/`**
10. **Integration testing and CI validation**

---

## Open Questions / Future Work

1. **Plan Agent Customization:** Should we create a custom system prompt for the Plan subagent, or rely on the default? (Decision: Use default for now; revisit if quality issues arise)

2. **Comment-based Clarifications:** The design initially included agent posting clarifying questions as issue comments. This is deferred to a later phase.

3. **Subtask Workflow:** When the plan PR is merged, a separate workflow (not this one) should convert the plan into Epic + sub-issues. Specification TBD.

4. **Approval Gate:** Currently, any REQUEST_CHANGES triggers re-planning. Should we add an "approved by maintainer" check to prevent infinite loops? (Decision: Deferred; can add in future)

---

## Files Modified/Created

**New files:**
- `shipyard/commands/plan.py` (~400 LOC)
- `shipyard/utils/github_event.py` (~150 LOC)
- `shipyard/templates/plan-driver.yml` (~120 LOC)
- `tests/test_commands_plan.py` (~300 LOC)
- `tests/test_github_event.py` (~150 LOC)
- `docs/plan-workflow.md` (~200 LOC)
- `docs/superpowers/specs/2026-04-15-plan-label-workflow-design.md` (this file)

**Modified files:**
- `shipyard/cli.py` (+1 line: add plan command)
- `shipyard/commands/init.py` (+30 LOC: loop over both templates, add --skip-plan-driver flag)
- `tests/test_commands_init.py` (+40 LOC: test plan-driver.yml copying)
- `docs/workflow.md` (+section on Plan Driver Workflow)
- `CLAUDE.md` (+link to plan-workflow.md in docs table)

---

## Success Criteria

- [ ] `shipyard plan` command fully implemented with all options
- [ ] `extract-github-event` utility parses all event types correctly
- [ ] Plan generation via Agent SDK produces valid markdown plans
- [ ] Git operations (branch, commit, push) work correctly
- [ ] PR creation works; REQUEST_CHANGES triggers re-planning
- [ ] `plan-driver.yml` template is valid YAML and syntactically correct
- [ ] `shipyard init` copies both workflows with version substitution
- [ ] All tests pass; code coverage >90%
- [ ] Manual testing successful on test repo
- [ ] Documentation complete and reviewed

