import logging
from typing import Any, Optional

import httpx

from .exceptions import NotFoundOnGitHub
from .settings import settings
from .vcs_client import AbstractVCSClient, SourceInfo

_logger = logging.getLogger(__name__)


class GithubClient(AbstractVCSClient):
    """
    Concrete implementation of AbstractVCSClient for GitHub.
    This class encapsulates all GitHub-specific logic and API interactions.
    """
    
    def __init__(self, settings):
        self.settings = settings

    async def _github_request(self, method: str, url: str, json: Any = None) -> Any:
        """Make a request to the GitHub API."""
        async with httpx.AsyncClient() as client:
            full_url = f"https://api.github.com{url}"
            headers = {
                "Accept": "application/vnd.github.v3+json",
            }
            if self.settings.vcs_api_token:  # Use the generic token setting
                headers["Authorization"] = f"token {self.settings.vcs_api_token}"
            response = await client.request(method, full_url, headers=headers, json=json)
            if response.status_code == 404:
                raise NotFoundOnGitHub(f"GitHub URL not found: {full_url}.")
            response.raise_for_status()
            return response.json()

    async def get_source_info_from_k8s(self, build_name: str) -> Optional[SourceInfo]:
        """
        Reads Kubernetes annotations for a build name and converts them into a
        generic SourceInfo model specific to GitHub.
        """
        try:
            from . import k8s as k8s_module
            deployment = await k8s_module.read_deployment(build_name)
            if deployment is None:
                return None
            annotations = deployment.metadata.annotations
            return SourceInfo(
                provider=annotations.get("runboat/provider", "github"),
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
        Gathers source information by calling the GitHub API using provided
        repository, PR/MR/Review details, and SHA.

        :param repo_details: A dictionary containing all necessary raw details
                              (e.g., repo, target_branch, commit_sha, pr).
        :return: A fully populated SourceInfo instance.
        """
        repo = repo_details.get("repo")
        target_branch = repo_details.get("target_branch")
        commit_sha = repo_details.get("commit_sha")
        pr = repo_details.get("pr")

        if not repo:
            raise ValueError("Repository is required")

        source_branch = None
        review_url = None

        if pr:
            # Fetch PR details from GitHub API
            pr_data = await self._github_request("GET", f"/repos/{repo}/pulls/{pr}")
            source_branch = pr_data["head"]["ref"]
            target_branch = pr_data["base"]["ref"]
            commit_sha = pr_data["head"]["sha"]
            review_url = f"https://github.com/{repo}/pull/{pr}"
        elif target_branch and not commit_sha:
            # Fetch branch info from GitHub API to get the latest commit SHA
            branch_data = await self._github_request("GET", f"/repos/{repo}/git/ref/heads/{target_branch}")
            commit_sha = branch_data["object"]["sha"]
            source_branch = target_branch
        elif target_branch:
            source_branch = target_branch
        elif commit_sha:
            # Only commit SHA provided, no branch info available
            pass
        else:
            raise ValueError("At least one of target_branch, commit_sha, or pr must be provided")

        clone_url = f"https://github.com/{repo}.git"

        return SourceInfo(
            provider="github",
            repository_id=repo,
            repository_full_name=repo,
            repository_url=f"https://github.com/{repo}",
            source_kind="review_request" if pr else "branch",
            source_branch=source_branch,
            target_branch=target_branch,
            commit_sha=commit_sha,
            clone_url=clone_url,
            review_id=str(pr) if pr else None,
            review_url=review_url,
        )

    async def set_commit_status(self, source_info: SourceInfo, state: str, target_url: Optional[str] = None) -> None:
        """
        Sets the build status (success, failure, pending) on the commit SHA
        using the GitHub API.
        
        :param source_info: The SourceInfo object containing repo/SHA details.
        :param state: The required state (e.g., 'success', 'failure').
        :param target_url: Optional URL to point the status check to.
        """
        if self.settings.disable_commit_statuses:
            return
            
        # Validate that this is a GitHub source
        if source_info.provider != "github":
            raise ValueError("SourceInfo is not for GitHub")
            
        # https://docs.github.com/en/rest/reference/repos#create-a-commit-status
        try:
            await self._github_request(
                "POST",
                f"/repos/{source_info.repository_id}/statuses/{source_info.commit_sha}",
                json={
                    "state": state,
                    "target_url": target_url,
                    "context": "runboat/build",
                },
            )
        except httpx.HTTPStatusError as e:
            _logger.error(
                f"Failed to post GitHub commit status (code {e.response.status_code}):\n"
                f"{e.response.text}"
            )