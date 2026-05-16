import logging
from typing import Any, Optional

import httpx
from pydantic import BaseModel

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
        # This would typically involve reading from K8s API
        # For now, we'll return None to indicate this needs implementation
        # In a full implementation, this would read the deployment and extract
        # the GitHub-specific annotations to create a SourceInfo object
        return None

    async def get_source_info_from_repo_details(self, repo_details: dict) -> SourceInfo:
        """
        Gathers source information by calling the GitHub API using provided 
        repository, PR/MR/Review details, and SHA.
        
        :param repo_details: A dictionary containing all necessary raw details 
                              (e.g., source URL, PR number, owner, etc.).
        :return: A fully populated SourceInfo instance.
        """
        # Extract details from repo_details
        repo = repo_details.get("repo")
        target_branch = repo_details.get("target_branch")
        commit_sha = repo_details.get("commit_sha")
        pr = repo_details.get("pr")
        
        if not repo or not commit_sha:
            raise ValueError("Repository and commit SHA are required")
            
        # If we have a PR number, get PR-specific info
        if pr:
            pr_data = await self._github_request("GET", f"/repos/{repo}/pulls/{pr}")
            source_branch = pr_data["head"]["ref"]
            target_branch = pr_data["base"]["ref"]
            commit_sha = pr_data["head"]["sha"]
            review_url = f"https://github.com/{repo}/pull/{pr}"
        else:
            # For branch builds, we might need to get branch info
            if target_branch:
                branch_data = await self._github_request("GET", f"/repos/{repo}/git/ref/heads/{target_branch}")
                commit_sha = branch_data["object"]["sha"]
            source_branch = target_branch
            review_url = None
            
        # Construct clone URL
        clone_url = f"https://github.com/{repo}.git"
        if self.settings.vcs_api_token:
            clone_url = f"https://{self.settings.vcs_api_token}@github.com/{repo}.git"
            
        return SourceInfo(
            provider="github",
            repository_id=repo,
            repository_full_name=repo,  # GitHub uses owner/repo as full name
            repository_url=f"https://github.com/{repo}",
            source_kind="review_request" if pr else "branch",
            source_branch=source_branch,
            target_branch=target_branch,
            commit_sha=commit_sha,
            clone_url=clone_url,
            review_id=str(pr) if pr else None,
            review_url=review_url
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