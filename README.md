# Shipyard

Autonomous GitHub Actions pipeline that implements GitHub Issues using AI agents.

Writing implementation tasks one by one is slow, error-prone, and doesn't scale. Shipyard turns a markdown plan into a structured GitHub Issue board and then runs a CI pipeline that implements, reviews, and opens pull requests for each task — without human intervention between steps.

## Quickstart

You need Python 3.13+, the [`gh` CLI](https://cli.github.com/) authenticated to your GitHub account, and a `CLAUDE_CODE_OAUTH_TOKEN` secret added to your repository.

```bash
pip install shipyard

# Scaffold the CI workflows into your repo
shipyard init

# Add the OAuth secret
gh secret set CLAUDE_CODE_OAUTH_TOKEN --body "<your-token>"

# Write a plan, then parse and sync it
shipyard tasks -i my-plan.md -t "My Feature" -o tasks.json
shipyard sync -i tasks.json

# Label the epic issue "in-progress" to start the pipeline
gh issue edit <epic-number> --add-label in-progress
```

## Key features

- Converts a markdown plan into a GitHub Issue board with dependency edges.
- Runs an implementer → spec reviewer → code quality reviewer pipeline per task.
- Publishes a pull request for each batch of completed tasks automatically.
- Retries failed reviews within the same session before moving on.
- Uses GitHub Issues as the only persistent store — no external database.

## Links

- [Documentation](docs/README.md)
- [Architecture](docs/explanation/architecture.md)
- [CLI reference](docs/reference/cli.md)
- [How to run your first epic](docs/how-to/run-your-first-epic.md)
- [Changelog](CHANGELOG.md)
