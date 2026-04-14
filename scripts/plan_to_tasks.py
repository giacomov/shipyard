#!/usr/bin/env python3
"""Convert a superpowers-style markdown plan to tasks.json format."""

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ParsedTask:
    id: str
    subject: str
    description: str
    status: str = "pending"
    dependencies: list[str] = field(default_factory=list)


@dataclass
class ParsedPlan:
    title: str
    body: str
    tasks: list[ParsedTask]


def parse_plan(text: str) -> ParsedPlan:
    """Parse markdown plan text into a ParsedPlan."""
    title = _parse_title(text)
    body = _parse_goal(text)
    task_blocks = _split_task_blocks(text)
    raw_tasks = []
    for block in task_blocks:
        m = re.match(r"^### Task (\d+):\s*(.+)$", block, re.MULTILINE)
        if not m:
            continue
        task_id = m.group(1)
        raw_tasks.append((task_id, m.group(2).strip(), block))

    tasks = [_parse_task_block(task_id, subject, block)
             for task_id, subject, block in raw_tasks]
    return ParsedPlan(title=title, body=body, tasks=tasks)


def _parse_title(text: str) -> str:
    m = re.search(r"^# (.+)$", text, re.MULTILINE)
    return m.group(1).strip() if m else "Implementation Plan"


def _parse_goal(text: str) -> str:
    m = re.search(r"^\*\*Goal:\*\*\s*(.+)$", text, re.MULTILINE)
    return m.group(1).strip() if m else ""


def _split_task_blocks(text: str) -> list[str]:
    """Split on '### Task N:' boundaries (ignores those inside code fences)."""
    boundary_pattern = re.compile(r"^### Task \d+:", re.MULTILINE)

    # Find positions of ### Task N: lines that are NOT inside code fences
    lines = text.split("\n")
    in_fence = False
    char_pos = 0
    char_positions: list[int] = []  # char positions of task headers

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
        elif not in_fence and re.match(r"^### Task \d+:", line):
            char_positions.append(char_pos)
        char_pos += len(line) + 1  # +1 for the newline

    if not char_positions:
        return []

    blocks = []
    for i, start in enumerate(char_positions):
        end = char_positions[i + 1] if i + 1 < len(char_positions) else len(text)
        block = text[start:end].strip()
        if block:
            blocks.append(block)
    return blocks


def _parse_task_block(
    task_id: str, subject: str, block: str
) -> ParsedTask:
    deps = _parse_depends_on(block)
    description = _extract_description(block)
    return ParsedTask(id=task_id, subject=subject, description=description, dependencies=deps)


def _parse_depends_on(block: str) -> list[str]:
    """Extract dependency ids from a '**Depends on:**' line."""
    m = re.search(r"^\*\*Depends on:\*\*\s*(.+)$", block, re.MULTILINE)
    if not m:
        return []
    raw = m.group(1).strip()
    if raw.lower() in ("(none)", "none", ""):
        return []
    # Extract "Task N" patterns
    numbers = re.findall(r"Task\s+(\d+)", raw, re.IGNORECASE)
    if not numbers:
        return []
    # Unknown refs will be caught by validate_plan
    return numbers


def _extract_description(block: str) -> str:
    """Remove the task header and **Depends on:** line from the block."""
    lines = block.splitlines()
    filtered = []
    skip_next_blank = False
    for line in lines:
        # Skip the ### Task N: header line
        if re.match(r"^### Task \d+:", line):
            skip_next_blank = True
            continue
        # Skip the **Depends on:** line
        if re.match(r"^\*\*Depends on:\*\*", line):
            skip_next_blank = True
            continue
        if skip_next_blank and line.strip() == "":
            skip_next_blank = False
            continue
        skip_next_blank = False
        filtered.append(line)
    # Strip leading/trailing blank lines
    result = "\n".join(filtered).strip()
    return result


def validate_plan(plan: ParsedPlan) -> None:
    """Raise ValueError if any dependency id is not a known task id."""
    known_ids = {t.id for t in plan.tasks}
    for task in plan.tasks:
        for dep in task.dependencies:
            if dep not in known_ids:
                raise ValueError(
                    f"Task {task.id} has unknown dependency 'Task {dep}'. "
                    f"Known task ids: {sorted(known_ids)}"
                )


def plan_to_tasks_dict(plan: ParsedPlan) -> dict[str, object]:
    """Convert ParsedPlan to the tasks.json dict structure."""
    return {
        "title": plan.title,
        "body": plan.body,
        "tasks": [
            {
                "id": t.id,
                "subject": t.subject,
                "description": t.description,
                "status": t.status,
                "dependencies": t.dependencies,
            }
            for t in plan.tasks
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert markdown plan to tasks.json")
    parser.add_argument("--input", "-i", type=Path, help="Input markdown file (default: stdin)")
    parser.add_argument("--output", "-o", type=Path, help="Output JSON file (default: stdout)")
    args = parser.parse_args()

    if args.input:
        try:
            text = args.input.read_text()
        except FileNotFoundError:
            print(f"Error: input file not found: {args.input}", file=sys.stderr)
            sys.exit(1)
    else:
        text = sys.stdin.read()

    plan = parse_plan(text)
    try:
        validate_plan(plan)
    except ValueError as e:
        print(f"Validation error: {e}", file=sys.stderr)
        sys.exit(1)

    result = plan_to_tasks_dict(plan)
    output = json.dumps(result, indent=2)

    if args.output:
        args.output.write_text(output)
    else:
        print(output)


if __name__ == "__main__":
    main()
