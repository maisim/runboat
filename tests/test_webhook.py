import pytest
from fastapi.testclient import TestClient
from pytest_mock import MockerFixture

from runboat.app import app
from runboat.controller import controller
from runboat.vcs_client import SourceInfo
from runboat.webhooks import _verify_github_signature

client = TestClient(app)


def test_webhook_github_push(mocker: MockerFixture) -> None:
    mock = mocker.patch("fastapi.BackgroundTasks.add_task")
    response = client.post(
        "/webhooks/github",
        headers={
            "X-GitHub-Event": "push",
        },
        json={
            "repository": {"full_name": "oca/mis-builder"},
            "ref": "refs/heads/15.0",
            "after": "abcde",
        },
    )
    response.raise_for_status()
    expected_source_info = SourceInfo(
        provider="github",
        repository_id="oca/mis-builder",
        repository_full_name="oca/mis-builder",
        repository_url="https://github.com/oca/mis-builder",
        source_kind="branch",
        source_branch=None,
        target_branch="15.0",
        commit_sha="abcde",
        clone_url="https://github.com/oca/mis-builder.git",
        review_id=None,
        review_url=None,
    )
    mock.assert_called_with(
        controller.deploy_commit,
        expected_source_info,
    )


def test_webhook_github_push_unsupported_repo(mocker: MockerFixture) -> None:
    mock = mocker.patch("fastapi.BackgroundTasks.add_task")
    response = client.post(
        "/webhooks/github",
        headers={
            "X-GitHub-Event": "push",
        },
        json={
            "repository": {"full_name": "org/not-a-repo"},  # repo not in .env.test
            "ref": "refs/heads/15.0",
            "after": "abcde",
        },
    )
    response.raise_for_status()
    mock.assert_not_called()


@pytest.mark.parametrize("action", ["opened", "synchronize"])
def test_webhook_github_pr(action: str, mocker: MockerFixture) -> None:
    mock = mocker.patch("fastapi.BackgroundTasks.add_task")
    response = client.post(
        "/webhooks/github",
        headers={
            "X-GitHub-Event": "pull_request",
        },
        json={
            "action": action,
            "repository": {"full_name": "oca/mis-builder"},
            "pull_request": {
                "base": {
                    "ref": "15.0",
                },
                "head": {
                    "ref": "feature-branch",
                    "sha": "abcde",
                },
                "number": 381,
            },
        },
    )
    response.raise_for_status()
    expected_source_info = SourceInfo(
        provider="github",
        repository_id="oca/mis-builder",
        repository_full_name="oca/mis-builder",
        repository_url="https://github.com/oca/mis-builder",
        source_kind="review_request",
        source_branch="feature-branch",
        target_branch="15.0",
        commit_sha="abcde",
        clone_url="https://github.com/oca/mis-builder.git",
        review_id="381",
        review_url="https://github.com/oca/mis-builder/pull/381",
    )
    mock.assert_called_with(
        controller.deploy_commit,
        expected_source_info,
    )


@pytest.mark.parametrize("action", ["opened", "synchronize", "closed"])
def test_webhook_github_pr_unsupported_branch(
    action: str, mocker: MockerFixture
) -> None:
    mock = mocker.patch("fastapi.BackgroundTasks.add_task")
    response = client.post(
        "/webhooks/github",
        headers={
            "X-GitHub-Event": "pull_request",
        },
        json={
            "action": action,
            "repository": {"full_name": "oca/mis-builder"},
            "pull_request": {
                "base": {
                    "ref": "14.0",  # branch 14.0 not declared in .env.test
                },
                "number": 381,
                "head": {
                    "sha": "abcde",
                },
            },
        },
    )
    response.raise_for_status()
    mock.assert_not_called()


def test_webhook_github_pr_close(mocker: MockerFixture) -> None:
    mock = mocker.patch("fastapi.BackgroundTasks.add_task")
    response = client.post(
        "/webhooks/github",
        headers={
            "X-GitHub-Event": "pull_request",
        },
        json={
            "action": "closed",
            "repository": {"full_name": "oca/mis-builder"},
            "pull_request": {
                "base": {
                    "ref": "15.0",
                },
                "number": 381,
            },
        },
    )
    response.raise_for_status()
    mock.assert_called_with(
        controller.undeploy_builds,
        repo="oca/mis-builder",
        pr=381,
    )


def test_verify_github_signature() -> None:
    assert _verify_github_signature(None, None, b"body")  # no secret configured, ok
    assert not _verify_github_signature(
        None, b"secret", b"body"
    )  # no X-Hub-Signature-256
    assert not _verify_github_signature(
        "sha256=invalid-sig", b"secret", b"body"
    )  # no X-Hub-Signature-256
    assert _verify_github_signature(
        "sha256=dc46983557fea127b43af721467eb9b3fde2338fe3e14f51952aa8478c13d355",
        b"secret",
        b"body",
    )
