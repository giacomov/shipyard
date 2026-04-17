Use this tool to create links between tasks.

## When to Use This Tool

When establishing dependencies between tasks you already created.

## Fields You Can Update

- **task_id**: the ID of the task you want to link to others
- **add_blocks**: Mark tasks that cannot start until this one completes
- **add_blocked_by**: Mark tasks that must complete before this one can start

## Examples

Set up task dependencies:
\`\`\`json
{"task_id": "2", "addBlockedBy": ["1"]}
\`\`\`