import pytest
from pytest_mock import MockerFixture

from runboat.gitlab_client import GitlabClient
from runboat.settings import Settings


def test_gitlab_encode_project_path() -> None:
    encoded = GitlabClient._encode_project_path("group/subgroup/project")
    assert encoded == "group%2Fsubgroup%2Fproject"


def test_gitlab_build_source_info() -> None:
    settings = Settings()
    client = GitlabClient(settings)
    result = client.build_source_info(
        repo="group/project",
        source_kind="review_request",
        commit_sha="abc123",
        source_branch="feature",
        target_branch="main",
        review_id="42",
        review_url="https://gitlab.com/group/project/-/merge_requests/42",
    )
    assert result.provider == "gitlab"
    assert result.repository_id == "group/project"
    assert result.repository_url == "https://gitlab.com/group/project"
    assert result.clone_url == "https://gitlab.com/group/project.git"
    assert result.source_kind == "review_request"
    assert result.review_id == "42"


def test_gitlab_build_source_info_self_hosted() -> None:
    settings = Settings(gitlab_base_url="https://gitlab.example.com")
    client = GitlabClient(settings)
    result = client.build_source_info(
        repo="group/project",
        source_kind="branch",
        commit_sha="abc123",
        target_branch="main",
    )
    assert result.repository_url == "https://gitlab.example.com/group/project"
    assert result.clone_url == "https://gitlab.example.com/group/project.git"


@pytest.mark.asyncio
async def test_gitlab_get_source_info_from_repo_details_mr(mocker: MockerFixture) -> None:
    settings = Settings()
    client = GitlabClient(settings)
    mock_request = mocker.patch.object(client, "_gitlab_request")
    mock_request.return_value = {
        "source_branch": "feature",
        "target_branch": "main",
        "sha": "abc123",
        "web_url": "https://gitlab.com/group/project/-/merge_requests/5",
    }
    result = await client.get_source_info_from_repo_details(
        {"repo": "group/project", "mr_iid": 5}
    )
    assert result.provider == "gitlab"
    assert result.repository_id == "group/project"
    assert result.source_kind == "review_request"
    assert result.source_branch == "feature"
    assert result.target_branch == "main"
    assert result.review_id == "5"


@pytest.mark.asyncio
async def test_gitlab_get_source_info_from_repo_details_branch(mocker: MockerFixture) -> None:
    settings = Settings()
    client = GitlabClient(settings)
    mock_request = mocker.patch.object(client, "_gitlab_request")
    mock_request.return_value = {
        "commit": {"id": "def456"},
    }
    result = await client.get_source_info_from_repo_details(
        {"repo": "group/project", "target_branch": "15.0"}
    )
    assert result.provider == "gitlab"
    assert result.repository_id == "group/project"
    assert result.source_kind == "branch"
    assert result.target_branch == "15.0"
    assert result.commit_sha == "def456"
