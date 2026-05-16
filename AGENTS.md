# runboat Agent Instructions

This repository implements Runboat, a Kubernetes operator for managing Odoo builds. The system relies heavily on Kubernetes resource management (labels/annotations) for state tracking.

## General Workflow Quirks
*   **Development Environment Setup:** Start by setting environment variables from `.env.sample`. Then, install uv and run: `uv sync --extra test`.
*   **Running the Application:** Use `uvicorn runboat.app:app --log-config=log-config.yaml`.
*   **Testing:** Run tests with `pytest`. Test environment variables are read from `.env.test`.
*   **Production Running:** Use `gunicorn -w 1 -k runboat.uvicorn.RunboatUvicornWorker runboat.app:app` (Note: Only 1 worker is recommended).

## Core Architectural Details
*   **State Management:** All build state is managed entirely through Kubernetes resources (labels and annotations), not in the application's memory.
*   **Build Identification:** All resources related to a single build must carry the label `runboat/build`, with the unique build name as its value.
*   **Kubernetes Lifecycle:** The deployment process follows a strict sequence managed by the controller:
    1.  `deployment` (resources creation)
    2.  `initialization` (job: checks out repo, installs dependencies, sets up database/addons)
    3.  `start` (updates scaling to 1)
    4.  `stop` (updates resources before scaling down to 0)
    5.  `cleanup` (job: drops database and deletes resources)
*   **Job Labeling:** Initialization jobs must have the label `runboat/job-kind=initialize`, and cleanup jobs must have the label `runboat/job-kind=cleanup`.
*   **Deployment Annotations:** Deployments require specific annotations to track metadata (v2 schema):
    *   `runboat/provider`: VCS provider name (e.g. `github`, `gitlab`).
    *   `runboat/repository-id`: provider-scoped repository identifier.
    *   `runboat/repository-url`: permanent repository URL.
    *   `runboat/source-kind`: `branch` or `review_request`.
    *   `runboat/source-branch`: source branch name.
    *   `runboat/target-branch`: target/destination branch name.
    *   `runboat/commit-sha`: commit SHA.
    *   `runboat/clone-url`: clone URL used by the CI system.
    *   `runboat/review-id`: review request identifier (string), if applicable.
    *   `runboat/review-url`: URL to the review request, if applicable.

## Tooling
*   The primary interaction point for starting a build is via the REST API (documented at `/docs`).
