# Task Format

This document describes the markdown plan syntax, the JSON schemas produced and consumed by shipyard, and a complete round-trip example.

## Markdown Plan Syntax

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

### Parsing Rules

| Element | Rule |
|---------|------|
| Plan title | First `# Heading` line in the file |
| Goal | `**Goal:**` line immediately following it |
| Task header | `### Task N: Title` where `N` is an integer |
| Dependencies | `**Depends on:** Task 1, Task 3` (or `(none)`) |
| Task description | All content in the task block except the header and `**Depends on:**` line |

- Task headers inside code fences (` ``` ` or `~~~`) are ignored.
- Dependency values are extracted by regex: `Task\s+(\d+)` (case-insensitive).
- Unknown dependency IDs cause a validation error before any JSON is emitted.

## JSON Task Schema

Output of `shipyard tasks`. This is also the input format for `shipyard sync`.

```json
{
  "title": "string — from the # heading",
  "body": "string — from **Goal:**",
  "tasks": [
    {
      "id": "string — the task number as a string (e.g. \"1\")",
      "subject": "string — the title after 'Task N:'",
      "description": "string — full task body without header/depends-on lines",
      "status": "string — always \"pending\" from the parser",
      "dependencies": ["string"] // task ids, e.g. ["1", "3"]
    }
  ]
}
```

**Field notes:**
- `id` is a string, not an integer (`"1"` not `1`).
- `dependencies` contains string ids, not issue numbers.
- `status` is always `"pending"` when output by `shipyard tasks`; it is informational and not used by `shipyard sync`.

## Work JSON Schema

Output of `shipyard find-work`. This is the input to `shipyard execute` via `$WORK_JSON`.

```json
{
  "epic_number": 42,
  "epic_title": "string — title of the epic GitHub Issue",
  "epic_body": "string — body of the epic GitHub Issue",
  "repo": "owner/repo",
  "issues": [
    {
      "number": 43,
      "title": "string — title of the sub-issue",
      "body": "string — body of the sub-issue"
    }
  ]
}
```

`issues` contains only **open, unblocked** sub-issues (no open blockers).

## Round-Trip Example

### 1. Markdown Plan (`plan.md`)

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
shipyard tasks -i plan.md
```

```json
{
  "title": "Sample Feature Implementation Plan",
  "body": "Build something simple for testing the parser.",
  "tasks": [
    {
      "id": "1",
      "subject": "Setup",
      "description": "Create the project scaffold.\n\n- [ ] **Step 1: Write the test**\n...",
      "status": "pending",
      "dependencies": []
    },
    {
      "id": "2",
      "subject": "Implementation",
      "description": "Implement the main feature using the scaffold from Task 1.\n...",
      "status": "pending",
      "dependencies": ["1"]
    }
  ]
}
```

### 3. GitHub Issues

```bash
shipyard sync -i tasks.json
```

Creates:
- Epic issue #10: "Sample Feature Implementation Plan" with `in-progress` label
- Sub-issue #11: "Setup"
- Sub-issue #12: "Implementation" — blocked by #11

### 4. Work Payload (produced by `find-work` after #11 is closed)

```json
{
  "epic_number": 10,
  "epic_title": "Sample Feature Implementation Plan",
  "epic_body": "Build something simple for testing the parser.",
  "repo": "myorg/myrepo",
  "issues": [
    {
      "number": 12,
      "title": "Implementation",
      "body": "Implement the main feature using the scaffold from Task 1.\n..."
    }
  ]
}
```

Issue #12 appears here because its only blocker (#11) is now closed.
