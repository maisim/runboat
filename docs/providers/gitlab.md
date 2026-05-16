# GitLab Provider

Runboat supports GitLab as a VCS provider for triggering builds from pushes and merge
requests, and for posting commit status checks.

## Configuration

### Environment Variables

| Variable | Purpose |
|----------|---------|
| `RUNBOAT_VCS_API_TOKEN` | GitLab personal access token with `api` scope |
| `RUNBOAT_VCS_WEBHOOK_SECRET` | Shared token used to verify webhook payloads |

The token must have at least the `api` scope to:
- Read branch and merge request information
- Post commit status checks

### Webhook Setup

1.  Go to your repository **Settings → Webhooks**.
2.  **URL:** `https://your-runboat-instance/webhooks/gitlab`
3.  **Secret token:** set this to the same value as `RUNBOAT_VCS_WEBHOOK_SECRET`
4.  **Events:** select **Push events** and **Merge request events**
5.  Mark **Enable SSL verification** (if using HTTPS) and **Add webhook**

### Supported Webhook Events

| Event | Actions | Build Action |
|-------|---------|--------------|
| `Push Hook` | — | Deploy new build for the pushed commit |
| `Merge Request Hook` | `open`, `reopen`, `update` | Deploy new build |
| `Merge Request Hook` | `merge`, `close` | Undeploy existing build |

## Annotation Values

When creating a build from a GitLab event, the build's Kubernetes annotations contain:

| Annotation | Value |
|------------|-------|
| `runboat/provider` | `gitlab` |
| `runboat/repository-id` | `group/subgroup/project` (full path) |
| `runboat/source-kind` | `branch` or `review_request` |
| `runboat/source-branch` | Source branch name |
| `runboat/target-branch` | Target branch name |
| `runboat/review-id` | Merge request IID (as string) |
| `runboat/review-url` | `https://gitlab.com/group/project/-/merge_requests/{iid}` |
| `runboat/commit-sha` | Full commit SHA |
| `runboat/clone-url` | `https://gitlab.com/group/project.git` |

## URL Patterns

- Repository: `https://gitlab.com/{repository_id}`
- Merge request: `https://gitlab.com/{repository_id}/-/merge_requests/{review_id}`
- Commit: `https://gitlab.com/{repository_id}/-/commit/{sha}`
- Clone: `https://gitlab.com/{repository_id}.git`

## Project Path Encoding

GitLab API endpoints require URL-encoded project paths. For example,
`group/subgroup/project` becomes `group%2Fsubgroup%2Fproject` when making API
calls. This encoding is handled internally by the `GitlabClient`.

## Self-Hosted GitLab

Runboat supports self-hosted GitLab instances. Configure the base URL with the
`RUNBOAT_GITLAB_BASE_URL` environment variable:

| Variable | Purpose | Default |
|----------|---------|---------|
| `RUNBOAT_GITLAB_BASE_URL` | Base URL of your GitLab instance | `https://gitlab.com` |

Example for a self-hosted instance at `gitlab.example.com`:

```
RUNBOAT_GITLAB_BASE_URL=https://gitlab.example.com
```

The API URL is derived automatically as `{base_url}/api/v4`.
Clone URLs and repository URLs use `{base_url}` directly.

## Limitations

- The token must have `api` scope to read repository data and post commit statuses.
- Git submodules are not handled.
