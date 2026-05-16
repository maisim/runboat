import hmac
import logging
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Header, Request

from .controller import controller
from .settings import settings
from .vcs_client import SourceInfo

_logger = logging.getLogger(__name__)

router = APIRouter()


def _verify_github_signature(
    x_hub_signature_256: str | None, secret: bytes | None, body: bytes
) -> bool:
    """Verify the GitHub webhook signature using HMAC-SHA256."""
    if not secret:
        return True
    if not x_hub_signature_256:
        _logger.warning("Got payload without X-Hub-Signature-256")
        return False
    signature = "sha256=" + hmac.new(secret, body, "sha256").hexdigest()
    if not hmac.compare_digest(signature, x_hub_signature_256):
        _logger.warning("Got payload with invalid X-Hub-Signature-256")
        return False
    return True


@router.post("/webhooks/github")
async def receive_github_payload(
    background_tasks: BackgroundTasks,
    request: Request,
    x_github_event: Annotated[str, Header(...)],
    x_hub_signature_256: Annotated[str | None, Header(...)] = None,
) -> None:
    """Receive GitHub webhook payload and trigger builds."""
    body = await request.body()
    if not _verify_github_signature(
        x_hub_signature_256, settings.vcs_webhook_secret, body
    ):
        return
    payload = await request.json()
    if x_github_event == "pull_request":
        repo = payload["repository"]["full_name"]
        target_branch = payload["pull_request"]["base"]["ref"]
        if not settings.is_repo_and_branch_supported(repo, target_branch):
            _logger.debug(
                "Ignoring %s payload for unsupported repo %s or target branch %s",
                x_github_event,
                repo,
                target_branch,
            )
            return
        if payload["action"] in ("opened", "synchronize"):
            pr_number = payload["pull_request"]["number"]
            source_info = SourceInfo(
                provider="github",
                repository_id=repo,
                repository_full_name=repo,
                repository_url=f"https://github.com/{repo}",
                source_kind="review_request",
                source_branch=payload["pull_request"]["head"]["ref"],
                target_branch=target_branch,
                commit_sha=payload["pull_request"]["head"]["sha"],
                clone_url=f"https://github.com/{repo}.git",
                review_id=str(pr_number),
                review_url=f"https://github.com/{repo}/pull/{pr_number}",
            )
            background_tasks.add_task(
                controller.deploy_commit,
                source_info,
            )
        elif payload["action"] in ("closed",):
            background_tasks.add_task(
                controller.undeploy_builds,
                repo=repo,
                pr=payload["pull_request"]["number"],
            )
    elif x_github_event == "push":
        repo = payload["repository"]["full_name"]
        target_branch = payload["ref"].split("/")[-1]
        if not settings.is_repo_and_branch_supported(repo, target_branch):
            _logger.debug(
                "Ignoring %s payload for unsupported repo %s or target branch %s",
                x_github_event,
                repo,
                target_branch,
            )
            return
        source_info = SourceInfo(
            provider="github",
            repository_id=repo,
            repository_full_name=repo,
            repository_url=f"https://github.com/{repo}",
            source_kind="branch",
            source_branch=None,
            target_branch=target_branch,
            commit_sha=payload["after"],
            clone_url=f"https://github.com/{repo}.git",
            review_id=None,
            review_url=None,
        )
        background_tasks.add_task(
            controller.deploy_commit,
            source_info,
        )


@router.post("/webhooks/gitlab")
async def receive_gitlab_payload(
    background_tasks: BackgroundTasks,
    request: Request,
    x_gitlab_event: Annotated[str | None, Header(...)] = None,
    x_gitlab_token: Annotated[str | None, Header(...)] = None,
) -> None:
    """Receive GitLab webhook payload and trigger builds."""
    # Simple token verification (GitLab uses a shared token)
    if settings.vcs_webhook_secret:
        token = settings.vcs_webhook_secret
        if isinstance(token, bytes):
            token = token.decode()
        if x_gitlab_token != token:
            _logger.warning("Got GitLab webhook with invalid token")
            return

    body = await request.body()
    payload = await request.json()
    event = x_gitlab_event or payload.get("event_type", "")

    if event == "Merge Request Hook":
        repo = payload["project"]["path_with_namespace"]
        mr = payload["object_attributes"]
        target_branch = mr["target_branch"]
        if not settings.is_repo_and_branch_supported(repo, target_branch):
            _logger.debug(
                "Ignoring GitLab MR payload for unsupported repo %s or target branch %s",
                repo, target_branch,
            )
            return
        action = mr["action"]
        if action in ("open", "update", "reopen"):
            source_info = SourceInfo(
                provider="gitlab",
                repository_id=repo,
                repository_full_name=repo,
                repository_url=f"https://gitlab.com/{repo}",
                source_kind="review_request",
                source_branch=mr["source_branch"],
                target_branch=target_branch,
                commit_sha=mr["last_commit"]["id"],
                clone_url=f"https://gitlab.com/{repo}.git",
                review_id=str(mr["iid"]),
                review_url=mr.get("url"),
            )
            background_tasks.add_task(
                controller.deploy_commit,
                source_info,
            )
        elif action in ("merge", "close"):
            background_tasks.add_task(
                controller.undeploy_builds,
                repo=repo,
                pr=mr["iid"],
            )
    elif event == "Push Hook":
        repo = payload["project"]["path_with_namespace"]
        target_branch = payload["ref"].split("/")[-1]
        if not settings.is_repo_and_branch_supported(repo, target_branch):
            _logger.debug(
                "Ignoring GitLab push payload for unsupported repo %s or target branch %s",
                repo, target_branch,
            )
            return
        source_info = SourceInfo(
            provider="gitlab",
            repository_id=repo,
            repository_full_name=repo,
            repository_url=f"https://gitlab.com/{repo}",
            source_kind="branch",
            source_branch=None,
            target_branch=target_branch,
            commit_sha=payload["after"],
            clone_url=f"https://gitlab.com/{repo}.git",
            review_id=None,
            review_url=None,
        )
        background_tasks.add_task(
            controller.deploy_commit,
            source_info,
        )
