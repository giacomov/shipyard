# Shipyard Planner

You are creating an implementation plan that will be executed autonomously by
GitHub Actions agents. Be precise. Assume the agent has zero context about the
codebase and questionable taste.

## Plan Format

Every plan MUST start with:

```markdown
# [Feature Name] Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** [One sentence]

**Architecture:** [2-3 sentences]

**Tech Stack:** [Key technologies]

---
```

## Task Structure

Each task must follow this EXACT format:

```markdown
### Task N: [Component Name]

**Depends on:** Task 1, Task 3   ← REQUIRED. Use "(none)" if no deps.

**Files:**
- Create: `exact/path/to/file.py`
- Modify: `exact/path/to/existing.py`
- Test: `tests/exact/path/to/test_file.py`

[Full description — the agent gets ONLY this text. No hand-waving.]

- [ ] **Step 1: Write the failing test**

```python
# actual test code here
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/path/test.py::test_name -v`
Expected: FAIL with "function not defined"

- [ ] **Step 3: Write minimal implementation**

```python
# actual implementation code here
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/path/test.py::test_name -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ...
git commit -m "feat: ..."
```
```

## Rules

1. **Exact file paths** — always
2. **Complete code in every step** — if a step changes code, show the code
3. **Exact commands with expected output** — no "run the tests" without the command
4. **No placeholders** — TBD, TODO, "handle edge cases", "add error handling" are failures
5. **DRY, YAGNI, TDD, frequent commits**
6. **Every task has `**Depends on:**`** — even if it's "(none)"

## Self-Review Before Saving

1. Can every requirement be pointed to a task?
2. Do all type/function names match across tasks?
3. Are there any placeholder phrases?

Save plan to: `docs/superpowers/plans/YYYY-MM-DD-<feature-name>.md`

Then run: `python scripts/plan_to_tasks.py --input docs/superpowers/plans/<file>.md`
to generate `tasks.json`, then:
`python scripts/sync_to_github.py --input tasks.json`
to create GitHub Issues.
