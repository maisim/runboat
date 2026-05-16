import pytest

from runboat.vcs_client import get_vcs_client


def test_get_vcs_client_github() -> None:
    client = get_vcs_client("github", None)
    from runboat.github_client import GithubClient
    assert isinstance(client, GithubClient)


def test_get_vcs_client_gitlab() -> None:
    client = get_vcs_client("gitlab", None)
    from runboat.gitlab_client import GitlabClient
    assert isinstance(client, GitlabClient)


def test_get_vcs_client_unsupported() -> None:
    with pytest.raises(ValueError, match="Unsupported VCS provider"):
        get_vcs_client("bitbucket", None)
