Use this tool to create links between tasks.

## When to Use This Tool

When establishing dependencies between tasks you already created.

## Fields You Can Update

- **task_id**: the ID of the task you want to link to others
- **add_blocked_by**: Mark tasks that must complete before this one can start

## Examples

Set up task dependencies:
\`\`\`json
{"task_id": "3", "add_blocked_by": ["1", "2"]}
\`\`\`