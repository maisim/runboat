import logging
from typing import Any, Optional
from urllib.parse import quote

import httpx

from .exceptions import ClientError
from .models import SourceInfo
from .settings import settings
from .vcs_client import AbstractVCSClient

_logger = logging.getLogger(__name__)


class NotFoundOnGitLab(ClientError):
    pass


class GitlabClient(AbstractVCSClient):
    """
    Concrete implementation of AbstractVCSClient for GitLab.
    """

    def __init__(self, settings):
        self.settings = settings

    @staticmethod
    def _encode_project_path(repo: str) -> str:
        """URL-encode the project path (e.g. 'group/subgroup/project')."""
        return quote(repo, safe="")

    async def _gitlab_request(self, method: str, url: str, json: Any = None) -> Any:
        """Make a request to the GitLab API."""
        async with httpx.AsyncClient() as client:
            full_url = f"https://gitlab.com/api/v4{url}"
            headers = {
                "Accept": "application/json",
            }
            if self.settings.vcs_api_token:
                headers["PRIVATE-TOKEN"] = self.settings.vcs_api_token
            response = await client.request(method, full_url, headers=headers, json=json)
            if response.status_code == 404:
                raise NotFoundOnGitLab(f"GitLab URL not found: {full_url}.")
            response.raise_for_status()
            return response.json()

    async def get_source_info_from_k8s(self, build_name: str) -> Optional[SourceInfo]:
        """
        Reads Kubernetes annotations for a build name and converts them into a
        generic SourceInfo model specific to GitLab.
        """
        try:
            from . import k8s as k8s_module
            deployment = await k8s_module.read_deployment(build_name)
            if deployment is None:
                return None
            annotations = deployment.metadata.annotations
            return SourceInfo(
                provider=annotations.get("runboat/provider", "gitlab"),
                repository_id=annotations.get("runboat/repository-id", ""),
                repository_full_name=annotations.get("runboat/repository-full-name"),
                repository_url=annotations.get("runboat/repository-url"),
                source_kind=annotations.get("runboat/source-kind", "branch"),
                source_branch=annotations.get("runboat/source-branch"),
                target_branch=annotations.get("runboat/target-branch"),
                commit_sha=annotations.get("runboat/commit-sha", ""),
                clone_url=annotations.get("runboat/clone-url", ""),
                review_id=annotations.get("runboat/review-id"),
                review_url=annotations.get("runboat/review-url"),
            )
        except Exception as e:
            _logger.error(f"Failed to read SourceInfo from K8s for build {build_name}: {e}")
            return None

    async def get_source_info_from_repo_details(self, repo_details: dict) -> SourceInfo:
        """
        Gathers source information by calling the GitLab API using provided
        repository, MR details, and SHA.
        """
        repo = repo_details.get("repo")
        target_branch = repo_details.get("target_branch")
        commit_sha = repo_details.get("commit_sha")
        mr_iid = repo_details.get("mr_iid")

        if not repo:
            raise ValueError("Repository is required")

        encoded_repo = self._encode_project_path(repo)
        source_branch = None
        review_url = None

        if mr_iid:
            mr_data = await self._gitlab_request(
                "GET", f"/projects/{encoded_repo}/merge_requests/{mr_iid}"
            )
            source_branch = mr_data["source_branch"]
            target_branch = mr_data["target_branch"]
            commit_sha = mr_data["sha"]
            review_url = mr_data.get("web_url")
        elif target_branch and not commit_sha:
            branch_data = await self._gitlab_request(
                "GET", f"/projects/{encoded_repo}/repository/branches/{target_branch}"
            )
            commit_sha = branch_data["commit"]["id"]
            source_branch = target_branch
        elif target_branch:
            source_branch = target_branch
        elif commit_sha:
            pass
        else:
            raise ValueError("At least one of target_branch, commit_sha, or mr_iid must be provided")

        clone_url = f"https://gitlab.com/{repo}.git"

        return SourceInfo(
            provider="gitlab",
            repository_id=repo,
            repository_full_name=repo,
            repository_url=f"https://gitlab.com/{repo}",
            source_kind="review_request" if mr_iid else "branch",
            source_branch=source_branch,
            target_branch=target_branch,
            commit_sha=commit_sha,
            clone_url=clone_url,
            review_id=str(mr_iid) if mr_iid else None,
            review_url=review_url,
        )

    async def set_commit_status(
        self, source_info: SourceInfo, state: str, target_url: Optional[str] = None
    ) -> None:
        """
        Sets the build status on the commit SHA using the GitLab API.
        """
        if self.settings.disable_commit_statuses:
            return

        if source_info.provider != "gitlab":
            raise ValueError("SourceInfo is not for GitLab")

        encoded_repo = self._encode_project_path(source_info.repository_id)

        # https://docs.gitlab.com/ee/api/commits.html#set-the-pipeline-status-of-a-commit
        try:
            await self._gitlab_request(
                "POST",
                f"/projects/{encoded_repo}/statuses/{source_info.commit_sha}",
                json={
                    "state": state,
                    "target_url": target_url,
                    "context": "runboat/build",
                },
            )
        except httpx.HTTPStatusError as e:
            _logger.error(
                f"Failed to post GitLab commit status (code {e.response.status_code}):\n"
                f"{e.response.text}"
            )
