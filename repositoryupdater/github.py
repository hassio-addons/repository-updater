"""
GitHub module.

This module extends the main PyGitHub class in order to add some extra
functionality.
"""

from git import Repo
from github import Github as PyGitHub
from github import Repository
from github.MainClass import DEFAULT_BASE_URL, DEFAULT_PER_PAGE, DEFAULT_TIMEOUT


class GitHub(PyGitHub):
    """Object for communicating with GitHub and cloning repositories."""

    token: str

    def __init__(self, login_or_token=None):
        """Initialize a new GitHub object."""
        super().__init__(login_or_token=login_or_token,)
        self.token = login_or_token

    def clone(self, repository: Repository, destination):
        """Clones a GitHub repository and returns a Git object."""
        environ = {
            "GIT_ASKPASS": "repository-updater-git-askpass",
            "GIT_USERNAME": self.token,
            "GIT_PASSWORD": "",
        }

        repo = Repo.clone_from(repository.clone_url, destination, None, environ)

        config = repo.config_writer()
        config.set_value("user", "email", self.get_user().email)
        config.set_value("user", "name", self.get_user().name)
        config.set_value("commit", "gpgsign", "false")

        return repo
