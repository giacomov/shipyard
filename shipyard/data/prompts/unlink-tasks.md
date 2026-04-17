Use this tool to remove links between tasks.

## When to Use This Tool

When removing dependencies between tasks you already created.

## Fields You Can Update

- **task_id**: the ID of the task you want to link to others
- **remove_blocked_by**: Remove the provided tasks from the list of dependencies of this task

## Examples

Remove the dependency on "2" from task "3":
\`\`\`json
{"task_id": "3", "remove_blocked_by": ["2"]}
\`\`\`