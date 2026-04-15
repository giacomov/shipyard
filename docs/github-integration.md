# GitHub Integration

Shipyard uses GitHub Issues as its persistent task board. This document explains how `shipyard sync` creates the board, how `shipyard find-work` reads it, and what GitHub permissions are required.

## How `shipyard sync` Creates the Board

`sync` makes a sequence of `gh` CLI calls:

1. **Create the epic issue** — `gh issue create --title <plan_title> --body <goal_text>`
   - Returns the issue URL; the issue number is extracted from the URL.
   - The database ID is fetched via `gh api repos/{owner}/{repo}/issues/{number}` (required for sub-issue linking).

2. **Create one sub-issue per task** — same `gh issue create` call for each task.
   - The issue body includes the task description, status emoji, and dependency IDs.

3. **Link sub-issues to the epic** — `gh api repos/{owner}/{repo}/issues/{epic}/sub_issues --method POST -F sub_issue_id={child_db_id}`
   - Uses the GitHub Issues preview API (`--preview issues`).

4. **Wire blocked-by edges** — `gh api repos/{owner}/{repo}/issues/{blocked}/dependencies/blocked_by --method POST -F issue_id={blocking_db_id}`
   - Soft-fails with a warning if the dependencies API returns 404 (not available on all plans/orgs).

5. **Apply `in-progress` label to the epic** — `gh issue edit {epic} --add-label in-progress`
   - Creates the label (color `0075ca`) if it does not already exist.

### `in-progress` Label Convention

The `in-progress` label on the epic issue is the signal that `find-work` uses to identify active epics. Applying this label also triggers the `epic-driver.yml` workflow (via the `issues: labeled` event). Removing it (or closing the epic) stops the automation.

## How `shipyard find-work` Resolves the Epic

The resolution strategy depends on `$EVENT_NAME`:

### `issues` or `workflow_dispatch`

`$ISSUE_NUMBER` is used directly as the epic number. No lookup is needed.

### `pull_request` (PR merged)

When a PR is merged, `find-work` needs to determine which epic it belongs to:

1. **Parse closing references** — scan `$PR_BODY` for `closes/fixes/resolves #N` patterns. Collects all referenced issue numbers.

2. **GraphQL parent lookup** — for each referenced issue number, query the GraphQL API for its parent issue. If the parent has the `in-progress` label, that parent is the epic.

3. **Fallback: label search** — if GraphQL lookup fails or returns nothing, list all open `in-progress` issues (up to 50) and check each one's sub-issues for a match.

If no epic is found, `has_work` is set to `false` and the workflow exits cleanly.

## How Unblocked Tasks Are Determined

Once the epic is resolved, `find-work` calls:

```
GET /repos/{owner}/{repo}/issues/{epic}/sub_issues
```

For each open sub-issue, it fetches:

```
GET /repos/{owner}/{repo}/issues/{sub}/dependencies/blocked_by
```

A sub-issue is **unblocked** if none of its blockers have `state == "open"`. Only unblocked sub-issues are included in the work payload.

This means: when a PR implementing issue #11 is merged and #11 closes, the next `find-work` run will find #12 (which was blocked by #11) as newly unblocked.

## Required GitHub Permissions

### For `shipyard sync` (local / CI)

The `gh` CLI must be authenticated with a token that has:
- `repo` scope (create issues, add labels)
- Access to the sub-issues and dependencies preview APIs (available on GitHub.com for public and private repos)

### For the `find-work` job

```yaml
permissions:
  contents: read
  issues: read
  pull-requests: read
```

### For the `execute` job

```yaml
permissions:
  contents: write     # push branches
  pull-requests: write  # create PRs
  issues: write       # post comments
  id-token: write     # OIDC (may be required by some setups)
```

The `GH_TOKEN` is provided automatically by GitHub Actions (`${{ github.token }}`). No additional personal access token is needed for the workflow itself.

The `CLAUDE_CODE_OAUTH_TOKEN` secret is a separate credential for the Claude Code agents — it authenticates the AI calls, not the GitHub API calls.
