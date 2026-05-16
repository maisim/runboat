import re
from pathlib import Path
from typing import Annotated, Optional
from pydantic import BaseModel, BeforeValidator, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .exceptions import RepoOrBranchNotSupported


def validate_path(v: str | None) -> Path | None:
    if not v:
        return None
    p = Path(v)
    if not p.is_dir():
        raise ValueError(f"Invalid path: {p}")
    return p


class BuildSettings(BaseModel):
    image: str  # container image:tag
    env: dict[str, str] = {}
    secret_env: dict[str, str] = {}
    template_vars: dict[str, str] = {}
    kubefiles_path: Annotated[Path | None, BeforeValidator(validate_path)] = None


class RepoSettings(BaseModel):
    repo: str  # regex
    branch: str  # regex
    builds: list[BuildSettings]

    @field_validator("builds")
    def validate_builds(cls, v: list[BuildSettings]) -> list[BuildSettings]:
        if len(v) != 1:
            raise ValueError(
                "One and only one build settings is allowed per repo/branch entry."
            )
        return v


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RUNBOAT_")

    # Configuration for supported repositories and branches.
    repos: list[RepoSettings]
    api_admin_user: str
    api_admin_passwd: str
    max_initializing: int = 2
    max_started: int = 6
    max_deployed: int = 10
    build_namespace: str
    build_domain: str
    build_env: dict[str, str] = {}
    build_secret_env: dict[str, str] = {}
    build_template_vars: dict[str, str] = {}
    build_default_kubefiles_path: Annotated[
        Path | None, BeforeValidator(validate_path)
    ] = None
    # Token for the VCS API (e.g., GitHub, GitLab)
    vcs_api_token: str | None = None
    vcs_webhook_secret: Optional[bytes] = None
    log_config: str | None = None
    base_url: str = "http://localhost:8000"
    additional_footer_html: str = ""
    disable_commit_statuses: bool = False
    deployment_resource_types: str = (
        "deployment,service,ingress,configmap,secret,pvc,job"
    )
    no_cleanup_job: bool = False

    def get_build_settings(self, repo: str, target_branch: str) -> list[BuildSettings]:
        """Find build settings for a given repo and target branch."""
        for repo_settings in self.repos:
            if not re.match(repo_settings.repo, repo, re.IGNORECASE):
                continue
            if not re.match(repo_settings.branch, target_branch):
                continue
            return repo_settings.builds
        raise RepoOrBranchNotSupported(
            f"Branch {target_branch} of {repo} not supported."
        )

    def is_repo_and_branch_supported(self, repo: str, target_branch: str) -> bool:
        """Check if a repo and target branch are supported."""
        try:
            self.get_build_settings(repo, target_branch)
        except RepoOrBranchNotSupported:
            return False
        else:
            return True


settings = Settings()
