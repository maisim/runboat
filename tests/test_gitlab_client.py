import pytest
from pytest_mock import MockerFixture

from runboat.gitlab_client import GitlabClient
from runboat.settings import Settings


def test_gitlab_encode_project_path() -> None:
    encoded = GitlabClient._encode_project_path("group/subgroup/project")
    assert encoded == "group%2Fsubgroup%2Fproject"


def test_gitlab_get_source_info_from_repo_details_mr(mocker: MockerFixture) -> None:
    settings = Settings()
    client = GitlabClient(settings)
    mock_request = mocker.patch.object(client, "_gitlab_request")
    mock_request.return_value = {
        "source_branch": "feature",
        "target_branch": "main",
        "sha": "abc123",
        "web_url": "https://gitlab.com/group/project/-/merge_requests/5",
    }
    result = client.get_source_info_from_repo_details(
        {"repo": "group/project", "mr_iid": 5}
    )
    assert result.provider == "gitlab"
    assert result.repository_id == "group/project"
    assert result.source_kind == "review_request"
    assert result.source_branch == "feature"
    assert result.target_branch == "main"
    assert result.review_id == "5"


def test_gitlab_get_source_info_from_repo_details_branch(mocker: MockerFixture) -> None:
    settings = Settings()
    client = GitlabClient(settings)
    mock_request = mocker.patch.object(client, "_gitlab_request")
    mock_request.return_value = {
        "commit": {"id": "def456"},
    }
    result = client.get_source_info_from_repo_details(
        {"repo": "group/project", "target_branch": "15.0"}
    )
    assert result.provider == "gitlab"
    assert result.repository_id == "group/project"
    assert result.source_kind == "branch"
    assert result.target_branch == "15.0"
    assert result.commit_sha == "def456"
