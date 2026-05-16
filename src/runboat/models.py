import datetime
import logging
import uuid
from enum import Enum
from typing import Optional

from kubernetes.client.models.v1_deployment import V1Deployment
from pydantic import BaseModel, ConfigDict

from . import k8s
from .github import GitHubStatusState
from .github_client import GithubClient
from .settings import settings
from .utils import slugify

_logger = logging.getLogger(__name__)


class SourceInfo(BaseModel):
    """Generic, provider-neutral representation of the source code input context for a build.

    This model replaces the vendor-specific CommitInfo, supporting multiple
    VCS providers with a unified interface.
    """
    provider: str  # e.g., "github", "gitlab"
    repository_id: str  # Canonical, provider-scoped identifier
    repository_full_name: str | None = None  # Fully qualified name (for display)
    repository_url: str | None = None  # Permanent URL of the repository
    source_kind: str  # "branch" or "review_request"
    source_branch: str | None = None  # The source ref or branch name
    target_branch: str | None = None  # The destination ref or branch name
    commit_sha: str  # The immutable SHA of the commit being built
    clone_url: str  # The clone URL used by the CI system
    review_id: str | None = None  # The unique raw ID for the review/PR/MR (must be string)
    review_url: str | None = None  # URL to the review request


class BuildEvent(str, Enum):
    modified = "upd"
    removed = "del"


class BuildStatus(str, Enum):
    stopped = "stopped"  # initialization succeeded and 0 replicas
    stopping = "stopping"  # 0 desired replicas but some are still running
    initializing = "initializing"  # to initialize or initializing
    starting = "starting"  # scaling up
    started = "started"  # running
    failed = "failed"  # initialization failed
    undeploying = "undeploying"  # undeploying, will be deleted after cleanup


class BuildInitStatus(str, Enum):
    todo = "todo"  # to initialize and start as soon as there is capacity
    started = "started"  # initialization job running
    succeeded = "succeeded"  # initialization job succeeded
    failed = "failed"  # initialization job failed


class Build(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    deployment_name: str
    source_info: SourceInfo  # Replaced CommitInfo with SourceInfo for provider-neutrality
    status: BuildStatus
    init_status: BuildInitStatus
    desired_replicas: int
    last_scaled: datetime.datetime
    created: datetime.datetime

    def __str__(self) -> str:
        return f"{self.slug} ({self.name})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Build):
            return False
        if self.name != other.name:
            return False
        # Compare based on core build identity fields
        return (
            self.source_info.commit_sha == other.source_info.commit_sha
            and self.status == other.status
            and self.init_status == other.init_status
            and self.desired_replicas == other.desired_replicas
            and self.last_scaled == other.last_scaled
        )

    @classmethod
    async def from_name(cls, build_name: str) -> Optional["Build"]:
        """Create a Build model by reading the k8s api."""
        deployment = await k8s.read_deployment(build_name)
        if deployment is None:
            return None
        return cls.from_deployment(deployment)

    @classmethod
    def from_deployment(cls, deployment: V1Deployment) -> "Build":
        """Translates a k8s V1Deployment object to a Build model."""
        
        # The annotations now MUST contain the new SourceInfo representation.
        annotations = deployment.metadata.annotations

        # Example of extracting SourceInfo from new annotations:
        try:
            # This assumes the K8s deployment has been correctly annotated with SourceInfo fields
            source_info = SourceInfo(
                provider=annotations["runboat/provider"],
                repository_id=annotations["runboat/repository-id"],
                repository_full_name=annotations.get("runboat/repository-full-name"),
                repository_url=annotations.get("runboat/repository-url"),
                source_kind=annotations["runboat/source-kind"],
                source_branch=annotations["runboat/source-branch"],
                target_branch=annotations["runboat/target-branch"],
                commit_sha=annotations["runboat/commit-sha"],
                clone_url=annotations["runboat/clone-url"],
                review_id=annotations.get("runboat/review-id"),
                review_url=annotations.get("runboat/review-url"),
            )
        except KeyError as e:
            raise ValueError(f"Required v2.0 source annotation missing in deployment: {e}. Cannot construct Build.")

        return Build(
            name=deployment.metadata.labels.get("runboat/build", ""),
            deployment_name=deployment.metadata.name,
            source_info=source_info,  # Use SourceInfo here
            init_status=annotations["runboat/init-status"],
            status=cls._status_from_deployment(deployment),
            desired_replicas=deployment.spec.replicas or 0,
            last_scaled=annotations.get("runboat/last-scaled")
            or deployment.metadata.creation_timestamp,
            created=deployment.metadata.creation_timestamp,
        )

    @classmethod
    def _status_from_deployment(cls, deployment: V1Deployment) -> BuildStatus:
        """Computes the BuildStatus based on the deployment's metadata and status."""
        if deployment.metadata.deletion_timestamp:
            return BuildStatus.undeploying
        init_status_str = deployment.metadata.annotations["runboat/init-status"]
        # Map string status to enum
        init_status = BuildInitStatus(init_status_str)
        if init_status in (BuildInitStatus.todo, BuildInitStatus.started):
            return BuildStatus.initializing
        elif init_status == BuildInitStatus.failed:
            return BuildStatus.failed
        elif init_status == BuildInitStatus.succeeded:
            replicas = deployment.spec.replicas
            if not replicas:
                if deployment.status.replicas:
                    return BuildStatus.stopping
                else:
                    return BuildStatus.stopped
            else:
                if deployment.status.available_replicas == replicas:
                    return BuildStatus.started
                else:
                    return BuildStatus.starting
        raise RuntimeError(f"Could not compute status of {deployment.metadata.name}.")

    @classmethod
    def make_slug(cls, source_info: SourceInfo) -> str:
        """Generates the build slug based on source_info."""
        # Use SourceInfo fields for slug calculation
        base = source_info.repository_id
        branch = source_info.target_branch or source_info.source_branch
        
        slug = f"{slugify(base)}-{slugify(branch)}"
        
        if source_info.review_id:
            slug = f"{slug}-review{slugify(source_info.review_id)}"
        
        # Append last 12 chars of SHA
        return f"{slug}-{source_info.commit_sha[:12]}"

    @property
    def slug(self) -> str:
        return self.make_slug(self.source_info)

    @property
    def deploy_link(self) -> str:
        """Link to the deployed build."""
        return f"http://{self.slug}.{settings.build_domain}"

    @property
    def deploy_link_mailhog(self) -> str:
        """Link to the deployed build's MailHog instance."""
        return f"http://{self.slug}.mail.{settings.build_domain}"

    @property
    def repo_target_branch_link(self) -> str:
        """Link to the repository's target branch on the VCS provider."""
        # Use source_info for the required repo/branch path
        return (
            f"https://{self.source_info.provider}.com/{self.source_info.repository_id}"
            f"/tree/{self.source_info.target_branch}"
        )

    @property
    def repo_review_link(self) -> str | None:
        """Link to the review request (PR/MR) on the VCS provider."""
        if not self.source_info.review_id:
            return None
        # Use provider-agnostic link construction for reviews
        return f"https://{self.source_info.provider}.com/{self.source_info.repository_id}/reviews/{self.source_info.review_id}"

    @property
    def repo_commit_link(self) -> str:
        """Link to the specific commit on the VCS provider."""
        # Link construction must use the primary commit SHA
        return f"https://{self.source_info.provider}.com/{self.source_info.repository_id}/commit/{self.source_info.commit_sha[:12]}"

    @property
    def webui_link(self) -> str:
        """Link to the build's page in the Runboat web UI."""
        return f"{settings.base_url}/builds/{self.name}"

    @property
    def live_link(self) -> str:
        """Link to the build's live view in the Runboat web UI."""
        return f"{self.webui_link}?live"

    async def init_log(self) -> str | None:
        """Get the logs for the initialization job."""
        return await k8s.log(self.name, job_kind=k8s.DeploymentMode.initialize)

    async def log(self) -> str | None:
        """Get the logs for the main build."""
        return await k8s.log(self.name, job_kind=None)

    @classmethod
    async def _deploy(
        cls, source_info: SourceInfo, name: str, slug: str, job_kind: k8s.DeploymentMode
    ) -> None:
        """Internal method to prepare for and handle a k8s.deploy()."""
        # This method needs updating to work with SourceInfo
        # For now, we'll assume a mapping from SourceInfo to the required details
        build_settings = settings.get_build_settings(
            source_info.repository_id, source_info.target_branch or ""
        )
        if build_settings:
            build_settings = build_settings[0]
        else:
            # Handle case where no settings are found
            raise ValueError("No build settings found for repository and branch")
        
        kubefiles_path = (
            build_settings.kubefiles_path or settings.build_default_kubefiles_path
        )
        
        # make_deployment_vars likely needs to be updated to handle SourceInfo
        deployment_vars = k8s.make_deployment_vars(
            job_kind,
            name,
            slug,
            source_info,  # Pass SourceInfo instead of CommitInfo
            build_settings,
        )
        await k8s.deploy(kubefiles_path, deployment_vars)

    @classmethod
    async def deploy(cls, source_info: SourceInfo) -> None:
        """Deploy a build, without starting it."""
        name = f"b{uuid.uuid4()}"
        slug = cls.make_slug(source_info)
        _logger.info(f"Deploying {slug} ({name}).")
        await cls._deploy(
            source_info, name, slug, job_kind=k8s.DeploymentMode.deployment
        )
        github_client = GithubClient(settings)
        await github_client.set_commit_status(
            source_info,
            GitHubStatusState.pending,
            target_url=None,
        )

    async def start(self) -> None:
        """Start build if init succeeded, or reinitialize if failed."""
        if self.status not in (BuildStatus.stopped, BuildStatus.stopping):
            _logger.info(f"Ignoring start command for {self} that is {self.status}.")
            return
        _logger.info(f"Starting {self} that was last scaled on {self.last_scaled}.")
        await self._deploy(
            self.source_info,
            self.name,
            self.slug,
            job_kind=k8s.DeploymentMode.start,
        )
        await self._patch(desired_replicas=1)

    async def stop(self) -> None:
        """Stop the build."""
        if self.status != BuildStatus.started:
            _logger.info(f"Ignoring stop command for {self} that is {self.status}.")
            return
        _logger.info(f"Stopping {self} that was last scaled on {self.last_scaled}.")
        await self._patch(desired_replicas=0)
        await self._deploy(
            self.source_info,
            self.name,
            self.slug,
            job_kind=k8s.DeploymentMode.stop,
        )

    async def undeploy(self) -> None:
        """Undeploy the build."""
        # To undeploy, we delete the deployment. Due to the finalizer, the deletion
        # will not be immediate, but the controller will notice the deletionTimestamp
        # and launch the cleanup job. When the cleanup job succeeds, the controller
        # removes all resources, and also removes the finalizer which allows kubernetes
        # to remove the deployment.
        await k8s.delete_deployment(self.deployment_name)

    async def redeploy(self) -> None:
        """Redeploy a build, to reinitialize it."""
        _logger.info(f"Redeploying {self}.")
        await k8s.kill_job(self.name, job_kind=k8s.DeploymentMode.cleanup)
        await k8s.kill_job(self.name, job_kind=k8s.DeploymentMode.initialize)
        await self._deploy(
            self.source_info,
            self.name,
            self.slug,
            job_kind=k8s.DeploymentMode.deployment,
        )
        github_client = GithubClient(settings)
        await github_client.set_commit_status(
            self.source_info,
            GitHubStatusState.pending,
            target_url=None,
        )

    async def initialize(self) -> None:
        """Launch the initialization job."""
        # Start initialization job. on_initialize_{started,succeeded,failed} callbacks
        # will follow from job events.
        _logger.info(f"Deploying initialize job for {self}.")
        await self._deploy(
            self.source_info,
            self.name,
            self.slug,
            job_kind=k8s.DeploymentMode.initialize,
        )

    async def _delete_deployment_resources(self) -> None:
        """Delete all resources associated with the deployment."""
        await k8s.delete_deployment_resources(self.name)
        _logger.debug("Removing finalizer for %s.", self)
        await self._patch(remove_finalizers=True, not_found_ok=True)

    async def cleanup(self) -> None:
        """Launch the cleanup job."""
        if settings.no_cleanup_job:
            await self._delete_deployment_resources()
            return
        # Kill the initialization job to reduce conflict with the cleanup job, such as
        # the database being created by the initialization after the cleanup job has
        # completed.
        await k8s.kill_job(self.name, job_kind=k8s.DeploymentMode.initialize)
        # Be sure the deployment is stopped.
        await self._patch(desired_replicas=0, not_found_ok=True)
        # Start cleanup job. on_cleanup_{started,succeeded,failed} callbacks will follow
        # from job events.
        _logger.info(f"Deploying cleanup job for {self}.")
        await self._deploy(
            self.source_info, self.name, self.slug, job_kind=k8s.DeploymentMode.cleanup
        )

    async def on_initialize_started(self) -> None:
        """Handle initialization job start."""
        if self.init_status == BuildInitStatus.started:
            return
        _logger.info(f"Initialization job started for {self}.")
        if await self._patch(init_status=BuildInitStatus.started, desired_replicas=0):
            github_client = GithubClient(settings)
            await github_client.set_commit_status(
                self.source_info,
                GitHubStatusState.pending,
                target_url=self.live_link,
            )

    async def on_initialize_succeeded(self) -> None:
        """Handle initialization job success."""
        if self.init_status == BuildInitStatus.succeeded:
            # Already marked as succeeded. We are probably here because the controller
            # is restarting, and is notified of existing initialization jobs.
            return
        _logger.info(f"Initialization job succeded for {self}, ready to start.")
        await self._deploy(
            self.source_info,
            self.name,
            self.slug,
            job_kind=k8s.DeploymentMode.stop,
        )
        if await self._patch(init_status=BuildInitStatus.succeeded):
            github_client = GithubClient(settings)
            await github_client.set_commit_status(
                self.source_info,
                GitHubStatusState.success,
                target_url=self.live_link,
            )

    async def on_initialize_failed(self) -> None:
        """Handle initialization job failure."""
        if self.init_status == BuildInitStatus.failed:
            # Already marked as failed. We are probably here because the controller is
            # restarting, and is notified of existing initialization jobs.
            return
        _logger.info(f"Initialization job failed for {self}.")
        await self._deploy(
            self.source_info,
            self.name,
            self.slug,
            job_kind=k8s.DeploymentMode.stop,
        )
        if await self._patch(init_status=BuildInitStatus.failed, desired_replicas=0):
            github_client = GithubClient(settings)
            await github_client.set_commit_status(
                self.source_info,
                GitHubStatusState.failure,
                target_url=self.live_link,
            )

    async def on_cleanup_started(self) -> None:
        """Handle cleanup job start."""
        _logger.info(f"Cleanup job started for {self}.")

    async def on_cleanup_succeeded(self) -> None:
        """Handle cleanup job success."""
        _logger.info(f"Cleanup job succeeded for {self}, deleting resources.")
        await self._delete_deployment_resources()

    async def on_cleanup_failed(self) -> None:
        """Handle cleanup job failure."""
        _logger.error(f"Cleanup job failed for {self}, manual intervention required.")

    async def _patch(
        self,
        init_status: BuildInitStatus | None = None,
        desired_replicas: int | None = None,
        remove_finalizers: bool = False,
        not_found_ok: bool = False,
    ) -> bool:
        """Apply a patch to the deployment."""
        ops: list[k8s.PatchOperation] = []
        if init_status is not None and init_status != self.init_status:
            ops.extend(
                [
                    {
                        "op": "replace",
                        "path": "/metadata/annotations/runboat~1init-status",
                        "value": init_status,
                    },
                ],
            )
        if desired_replicas is not None and desired_replicas != self.desired_replicas:
            ops.extend(
                [
                    {
                        "op": "replace",
                        "path": "/spec/replicas",
                        "value": desired_replicas,
                    },
                    {
                        "op": "replace",
                        "path": "/metadata/annotations/runboat~1last-scaled",
                        "value": datetime.datetime.utcnow()
                        .replace(microsecond=0)
                        .isoformat()
                        + "Z",
                    },
                ]
            )
        if remove_finalizers:
            ops.append(
                {
                    "op": "remove",
                    "path": "/metadata/finalizers",
                }
            )
        if ops:
            await k8s.patch_deployment(self.deployment_name, ops, not_found_ok)
            return True
        return False


class Repo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str

    @property
    def link(self) -> str:
        return f"https://github.com/{self.name}"
