from __future__ import annotations

import abc
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from runboat.models import SourceInfo


class AbstractVCSClient(abc.ABC):
    """
    Abstract base class for all VCS provider clients.
    Concrete implementations (e.g., GithubClient) must implement all abstract methods.
    """

    @abc.abstractmethod
    async def get_source_info_from_k8s(self, build_name: str) -> Optional[SourceInfo]:
        """
        Reads Kubernetes annotations for a build name and converts them into a
        generic SourceInfo model.
        """
        ...

    @abc.abstractmethod
    async def get_source_info_from_repo_details(self, repo_details: dict) -> SourceInfo:
        """
        Gathers source information by calling the native VCS API using provided
        repository, PR/MR/Review details, and SHA.
        """
        ...

    @abc.abstractmethod
    def build_source_info(
        self,
        repo: str,
        source_kind: str,
        commit_sha: str,
        *,
        source_branch: Optional[str] = None,
        target_branch: Optional[str] = None,
        review_id: Optional[str] = None,
        review_url: Optional[str] = None,
    ) -> SourceInfo:
        """
        Build a SourceInfo from known data without making API calls.
        Useful for webhook handlers that already have all payload fields.
        """
        ...

    @abc.abstractmethod
    async def set_commit_status(
        self, source_info: SourceInfo, state: str, target_url: Optional[str] = None
    ) -> None:
        """
        Sets the build status (success, failure, pending) on the commit SHA
        using the VCS provider's API.
        """
        ...


def get_vcs_client(provider: str, settings) -> AbstractVCSClient:
    """Factory: return the appropriate VCS client for the given provider."""
    if provider == "github":
        from .github_client import GithubClient
        return GithubClient(settings)
    if provider == "gitlab":
        from .gitlab_client import GitlabClient
        return GitlabClient(settings)
    raise ValueError(f"Unsupported VCS provider: {provider}")
