# Task format reference

This document describes the markdown plan syntax, the JSON schemas produced and consumed by shipyard, and a complete round-trip example.

## Markdown plan syntax

A plan is a single `.md` file with the following structure:

```markdown
# [Feature Name] Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: ...

**Goal:** One sentence describing what the plan achieves.

**Architecture:** 2–3 sentences.

**Tech Stack:** Key technologies.

---

### Task 1: First Component

**Depends on:** (none)

Full description of what the agent must implement. This is the only text
the agent sees — no hand-waving.

- [ ] **Step 1: Write the failing test**
...

### Task 2: Second Component

**Depends on:** Task 1

Description...
```

### Suggested plan structure

`shipyard tasks` uses an AI agent to read the plan file and extract tasks — there is no static regex parser or deterministic line-by-line processing. The structure shown in the example above is a recommended convention that the agent is likely to follow; it is not a strict requirement enforced by parsing rules.

Unknown dependency IDs are caught by `shipyard sync`'s `validate()` function, after `tasks.json` has already been written by `shipyard tasks`.

## JSON task schema

Output of `shipyard tasks`. This is also the input format for `shipyard sync`.

```json
{
  "title": "string — from the --title flag",
  "description": "string — full content of the input markdown plan",
  "tasks": {
    "1": {
      "task_id": "string — the task number as a string (e.g. \"1\")",
      "title": "string — task title",
      "description": "string — task description",
      "status": "string — always \"pending\"",
      "blocked_by": ["string"]
    }
  }
}
```

**Field notes:**
- `tasks` is a dict keyed by `task_id`, not an array.
- `task_id` is a string, not an integer (`"1"` not `1`).
- `blocked_by` is a list of `task_id` strings referencing other tasks.
- `status` is always `"pending"` when output by `shipyard tasks`; it is informational and not used by `shipyard sync`.
- `description` at the top level contains the full markdown plan content.

## Work JSON schema

Output of `shipyard find-work`. This is the input to `shipyard execute` via `-i FILE`. It uses the same `SubtaskList` / `Subtask` schema as `tasks.json`, with `epic_id` and `task_id` set to stringified GitHub issue numbers.

```json
{
  "epic_id": "42",
  "title": "string — title of the epic GitHub Issue",
  "description": "string — body of the epic GitHub Issue",
  "tasks": {
    "43": {
      "task_id": "43",
      "title": "string — title of the sub-issue",
      "description": "string — body of the sub-issue",
      "status": "pending",
      "blocked_by": []
    }
  }
}
```

`tasks` contains only **open, unblocked** sub-issues (no open blockers).

## Round-trip example

### 1. Markdown plan (`plan.md`)

```markdown
# Sample Feature Implementation Plan

**Goal:** Build something simple for testing the parser.

**Architecture:** Two tasks, one dependency.

**Tech Stack:** Python

---

### Task 1: Setup

**Depends on:** (none)

Create the project scaffold.

- [ ] **Step 1: Write the test**

```python
def test_scaffold():
    assert True
```

- [ ] **Step 2: Commit**

```bash
git commit -m "feat: scaffold"
```

### Task 2: Implementation

**Depends on:** Task 1

Implement the main feature using the scaffold from Task 1.
```

### 2. JSON (`tasks.json`)

```bash
shipyard tasks -i plan.md --title "Sample Feature Implementation Plan"
```

```json
{
  "title": "Sample Feature Implementation Plan",
  "description": "# Sample Feature Implementation Plan\n\n**Goal:** Build something simple ...",
  "tasks": {
    "1": {
      "task_id": "1",
      "title": "Setup",
      "description": "Create the project scaffold.\n\n- [ ] **Step 1: Write the test**\n...",
      "status": "pending",
      "blocked_by": []
    },
    "2": {
      "task_id": "2",
      "title": "Implementation",
      "description": "Implement the main feature using the scaffold from Task 1.\n...",
      "status": "pending",
      "blocked_by": ["1"]
    }
  }
}
```

### 3. GitHub Issues

```bash
shipyard sync -i tasks.json
```

Creates:
- Epic issue #10: "Sample Feature Implementation Plan"
- Sub-issue #11: "Setup"
- Sub-issue #12: "Implementation" — blocked by #11

### 4. Work payload (produced by `find-work` after #11 is closed)

```json
{
  "epic_id": "10",
  "title": "Sample Feature Implementation Plan",
  "description": "Build something simple for testing the parser.",
  "tasks": {
    "12": {
      "task_id": "12",
      "title": "Implementation",
      "description": "Implement the main feature using the scaffold from Task 1.\n...",
      "status": "pending",
      "blocked_by": []
    }
  }
}
```

Task "12" (issue #12) appears here because its only blocker (#11) is now closed.
