from enum import Enum


class GitHubStatusState(str, Enum):
    error = "error"
    failure = "failure"
    pending = "pending"
    success = "success"
