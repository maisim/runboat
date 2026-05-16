# Migration Guide: Runboat v1 to v2

This guide covers the breaking changes introduced in Runboat v2 and how to
migrate existing deployments, configuration, and webhooks.

## Overview

Runboat v2 introduces a provider-neutral VCS abstraction layer. GitHub-specific
concepts (`CommitInfo`, `runboat/pr`, `runboat/repo`, etc.) have been replaced
with generic equivalents (`SourceInfo`, `runboat/review-id`,
`runboat/repository-id`, etc.). This is a **breaking change** — v1 Kubernetes
resources are **not** compatible with the v2 controller.

## 1. Configuration Migration

### Environment Variables

| Old Variable | New Variable | Notes |
|---|---|---|
| `RUNBOAT_GITHUB_TOKEN` | `RUNBOAT_VCS_API_TOKEN` | Generic VCS API token |
| `RUNBOAT_GITHUB_WEBHOOK_SECRET` | `RUNBOAT_VCS_WEBHOOK_SECRET` | Generic webhook secret |

### Build Repo Settings

The `RepoSettings.repo` field still uses regex matching against the
`repository_id` (formerly `owner/repo`). No structural change is required, but
if you were relying on the GitHub-specific `owner/repo` format you should
verify your regex patterns work for your VCS provider's identifier format.

## 2. Kubernetes Resource Migration

### Old Annotation Schema (v1)

```yaml
metadata:
  annotations:
    runboat/repo: "owner/repo"
    runboat/target-branch: "15.0"
    runboat/pr: "123"
    runboat/git-commit: "abc123..."
```

### New Annotation Schema (v2)

```yaml
metadata:
  annotations:
    runboat/provider: "<vcs-provider>"       # e.g. "github", "gitlab"
    runboat/repository-id: "<repo-id>"       # e.g. "owner/repo" or "group/subgroup/project"
    runboat/repository-url: "<repo-url>"     # permanent URL to the repository
    runboat/source-kind: "review_request"    # "branch" or "review_request"
    runboat/source-branch: "feature-branch"  # source branch name
    runboat/target-branch: "15.0"            # destination branch name
    runboat/review-id: "123"                 # review request identifier (string)
    runboat/commit-sha: "abc123..."          # full commit SHA
    runboat/clone-url: "<clone-url>"         # clone URL for the repository
```

Provider-specific examples:

| Provider | `repository-url` | `clone-url` |
|----------|-----------------|-------------|
| GitHub   | `https://github.com/owner/repo` | `https://github.com/owner/repo.git` |
| GitLab   | `https://gitlab.com/group/project` | `https://gitlab.com/group/project.git` |

### Migration Strategy

v1 resources **will not** be automatically upgraded. You have two options:

**Option A — Clean slate (recommended)**
1.  Stop the v1 controller.
2.  Delete all existing build deployments:
    ```bash
    kubectl delete deployments -n runboat-builds -l runboat/build
    kubectl delete jobs -n runboat-builds -l runboat/build
    kubectl delete pods -n runboat-builds -l runboat/build
    ```
3.  Deploy the v2 controller.
4.  Existing builds will be recreated on the next webhook event or manual trigger.

**Option B — Selective cleanup**
1.  Keep the v1 controller running until active builds finish.
2.  Stop the v1 controller.
3.  Delete remaining build resources as above.
4.  Deploy the v2 controller.

> **Note:** The v2 controller's preflight check will warn about any resources
> with missing v2 annotations, but it will not automatically delete them.

## 3. Webhook Reconfiguration

### GitHub Webhooks

The `/webhooks/github` endpoint still accepts the same payload format. No
changes are required to your GitHub webhook configuration.

### GitLab Webhooks

The new `/webhooks/gitlab` endpoint accepts GitLab webhook payloads for
`Push Hook` and `Merge Request Hook` events. Configure your GitLab repository
to send webhooks to `https://your-runboat-instance/webhooks/gitlab` with the
webhook secret token matching `RUNBOAT_VCS_WEBHOOK_SECRET` (or `RUNBOAT_VCS_API_TOKEN`
for token-based verification).

### Internal Changes

Webhook handlers now construct `SourceInfo` objects instead of
`CommitInfo`. The payload parsing logic for each provider remains specific
to that provider's payload format.

## 4. REST API Changes

### Trigger Endpoints

The `/builds/trigger/branch` and `/builds/trigger/pr` endpoints retain their
existing signatures (`repo`, `branch` / `repo`, `pr`). The internal
implementation now uses the VCS client abstraction.

### Build Response Model

The build JSON response now uses `source_info` instead of `commit_info`:

```json
{
  "name": "b...",
  "source_info": {
    "provider": "<vcs-provider>",
    "repository_id": "<repo-id>",
    "repository_full_name": null,
    "repository_url": "<repo-url>",
    "source_kind": "review_request",
    "source_branch": "feature",
    "target_branch": "main",
    "commit_sha": "abc...",
    "clone_url": "<clone-url>",
    "review_id": "123",
    "review_url": "<review-url>"
  },
  ...
}
```

The `commit_info.repo` → `source_info.repository_id`
The `commit_info.pr` → `source_info.review_id`

## 5. Rollback

If you need to roll back to v1:
1.  Stop the v2 controller.
2.  Restore the v1 configuration (old environment variable names).
3.  Revert the `RUNBOAT_VCS_API_TOKEN` to `RUNBOAT_GITHUB_TOKEN`.
4.  Deploy the v1 controller.
5.  v2-annotated resources can be read by v1 components at the controller's
    discretion, but the old annotation keys must be present for full
    compatibility.
