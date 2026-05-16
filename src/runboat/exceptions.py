class ClientError(Exception):
    pass


class RepoNotSupported(ClientError):
    pass


class BranchNotFound(ClientError):
    pass


class NotFoundOnGitHub(ClientError):
    pass


class RepoOrBranchNotSupported(ClientError):
    pass


class RunboatVCSClientError(Exception):
    """Exception raised for errors in the VCS client abstraction layer."""
    pass
