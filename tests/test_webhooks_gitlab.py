from fastapi.testclient import TestClient
from pytest_mock import MockerFixture

from runboat.app import app
from runboat.controller import controller
from runboat.models import SourceInfo

client = TestClient(app)


def test_webhook_gitlab_push(mocker: MockerFixture) -> None:
    mock = mocker.patch("fastapi.BackgroundTasks.add_task")
    response = client.post(
        "/webhooks/gitlab",
        headers={
            "X-Gitlab-Event": "Push Hook",
        },
        json={
            "event_type": "push",
            "project": {"path_with_namespace": "oca/mis-builder"},
            "ref": "refs/heads/15.0",
            "after": "abcde",
        },
    )
    response.raise_for_status()
    expected_source_info = SourceInfo(
        provider="gitlab",
        repository_id="oca/mis-builder",
        repository_full_name="oca/mis-builder",
        repository_url="https://gitlab.com/oca/mis-builder",
        source_kind="branch",
        source_branch=None,
        target_branch="15.0",
        commit_sha="abcde",
        clone_url="https://gitlab.com/oca/mis-builder.git",
        review_id=None,
        review_url=None,
    )
    mock.assert_called_with(
        controller.deploy_commit,
        expected_source_info,
    )


def test_webhook_gitlab_mr_open(mocker: MockerFixture) -> None:
    mock = mocker.patch("fastapi.BackgroundTasks.add_task")
    response = client.post(
        "/webhooks/gitlab",
        headers={
            "X-Gitlab-Event": "Merge Request Hook",
        },
        json={
            "event_type": "merge_request",
            "project": {"path_with_namespace": "oca/mis-builder"},
            "object_attributes": {
                "action": "open",
                "source_branch": "feature-branch",
                "target_branch": "15.0",
                "iid": 42,
                "last_commit": {"id": "abcde"},
                "url": "https://gitlab.com/oca/mis-builder/-/merge_requests/42",
            },
        },
    )
    response.raise_for_status()
    expected_source_info = SourceInfo(
        provider="gitlab",
        repository_id="oca/mis-builder",
        repository_full_name="oca/mis-builder",
        repository_url="https://gitlab.com/oca/mis-builder",
        source_kind="review_request",
        source_branch="feature-branch",
        target_branch="15.0",
        commit_sha="abcde",
        clone_url="https://gitlab.com/oca/mis-builder.git",
        review_id="42",
        review_url="https://gitlab.com/oca/mis-builder/-/merge_requests/42",
    )
    mock.assert_called_with(
        controller.deploy_commit,
        expected_source_info,
    )


def test_webhook_gitlab_mr_close(mocker: MockerFixture) -> None:
    mock = mocker.patch("fastapi.BackgroundTasks.add_task")
    response = client.post(
        "/webhooks/gitlab",
        headers={
            "X-Gitlab-Event": "Merge Request Hook",
        },
        json={
            "event_type": "merge_request",
            "project": {"path_with_namespace": "oca/mis-builder"},
            "object_attributes": {
                "action": "close",
                "target_branch": "15.0",
                "iid": 42,
            },
        },
    )
    response.raise_for_status()
    mock.assert_called_with(
        controller.undeploy_builds,
        repo="oca/mis-builder",
        pr=42,
    )
