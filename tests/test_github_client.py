import pytest
from pytest_mock import MockerFixture

from runboat.github_client import GithubClient
from runboat.settings import Settings


def test_github_get_source_info_from_repo_details_pr(mocker: MockerFixture) -> None:
    settings = Settings()
    client = GithubClient(settings)
    mock_request = mocker.patch.object(client, "_github_request")
    mock_request.return_value = {
        "head": {"ref": "feature-branch", "sha": "abc123"},
        "base": {"ref": "main"},
    }
    result = client.get_source_info_from_repo_details(
        {"repo": "owner/repo", "pr": 42}
    )
    assert result.provider == "github"
    assert result.repository_id == "owner/repo"
    assert result.source_kind == "review_request"
    assert result.source_branch == "feature-branch"
    assert result.target_branch == "main"
    assert result.review_id == "42"


def test_github_get_source_info_from_repo_details_branch(mocker: MockerFixture) -> None:
    settings = Settings()
    client = GithubClient(settings)
    mock_request = mocker.patch.object(client, "_github_request")
    mock_request.return_value = {
        "object": {"sha": "def456"},
    }
    result = client.get_source_info_from_repo_details(
        {"repo": "owner/repo", "target_branch": "15.0"}
    )
    assert result.provider == "github"
    assert result.repository_id == "owner/repo"
    assert result.source_kind == "branch"
    assert result.target_branch == "15.0"
    assert result.commit_sha == "def456"


def test_github_get_source_info_from_repo_details_commit_only() -> None:
    settings = Settings()
    client = GithubClient(settings)
    result = client.get_source_info_from_repo_details(
        {"repo": "owner/repo", "commit_sha": "abc123"}
    )
    assert result.provider == "github"
    assert result.repository_id == "owner/repo"
    assert result.source_kind == "branch"
    assert result.commit_sha == "abc123"


def test_github_get_source_info_from_repo_details_missing_repo() -> None:
    settings = Settings()
    client = GithubClient(settings)
    with pytest.raises(ValueError, match="Repository is required"):
        client.get_source_info_from_repo_details({})


def test_github_get_source_info_from_repo_details_missing_all() -> None:
    settings = Settings()
    client = GithubClient(settings)
    with pytest.raises(ValueError, match="At least one of"):
        client.get_source_info_from_repo_details({"repo": "owner/repo"})
