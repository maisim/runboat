# GitHub Provider

Runboat supports GitHub as a VCS provider for triggering builds from pushes and pull
requests, and for posting commit status checks.

## Configuration

### Environment Variables

| Variable | Purpose |
|----------|---------|
| `RUNBOAT_VCS_API_TOKEN` | GitHub personal access token with `repo` scope |
| `RUNBOAT_VCS_WEBHOOK_SECRET` | Secret used to verify webhook payloads |

The token must have at least the `repo` scope to:
- Read branch and pull request information
- Post commit status checks

### Webhook Setup

1.  Go to your repository **Settings → Webhooks → Add webhook**.
2.  **Payload URL:** `https://your-runboat-instance/webhooks/github`
3.  **Content type:** `application/json`
4.  **Secret:** set this to the same value as `RUNBOAT_VCS_WEBHOOK_SECRET`
5.  **Events:** select **Push events** and **Pull request events**
6.  Mark **Active** and **Add webhook**

### Supported Webhook Events

| Event | Actions | Build Action |
|-------|---------|--------------|
| `push` | — | Deploy new build for the pushed commit |
| `pull_request` | `opened`, `synchronize` | Deploy new build |
| `pull_request` | `closed` | Undeploy existing build |

## Annotation Values

When creating a build from a GitHub event, the build's Kubernetes annotations contain:

| Annotation | Value |
|------------|-------|
| `runboat/provider` | `github` |
| `runboat/repository-id` | `owner/repo` (e.g., `oca/mis-builder`) |
| `runboat/source-kind` | `branch` or `review_request` |
| `runboat/source-branch` | Source branch name |
| `runboat/target-branch` | Target branch name |
| `runboat/review-id` | Pull request number (as string) |
| `runboat/review-url` | `https://github.com/owner/repo/pull/{number}` |
| `runboat/commit-sha` | Full commit SHA |
| `runboat/clone-url` | `https://github.com/owner/repo.git` |

## URL Patterns

- Repository: `https://github.com/{repository_id}`
- Pull request: `https://github.com/{repository_id}/pull/{review_id}`
- Commit: `https://github.com/{repository_id}/commit/{sha}`
- Clone: `https://github.com/{repository_id}.git`

## Limitations

- Only public and private repositories accessible by the token are supported.
- The token must have `repo` scope for private repos.
- Git submodules are not handled.
