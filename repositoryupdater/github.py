"""
GitHub module.

This module extends the main PyGitHub class in order to add some extra
functionality.
"""

from git import Repo
from github import Github as PyGitHub
from github import Repository


class GitHub(PyGitHub):
    """Object for communicating with GitHub and cloning repositories."""

    token: str

    def __init__(self, login_or_token=None, fallback_email=None):
        """Initialize a new GitHub object."""
        super().__init__(
            login_or_token=login_or_token,
        )
        self.token = login_or_token
        self.fallback_email = fallback_email

    def clone(self, repository: Repository, destination):
        """Clones a GitHub repository and returns a Git object."""
        environ = {
            "GIT_ASKPASS": "repository-updater-git-askpass",
            "GIT_USERNAME": self.token,
            "GIT_PASSWORD": "",
        }

        repo = Repo.clone_from(repository.clone_url, destination, None, environ)

        config = repo.config_writer()
        user = self.get_user()
        email = user.email or self.fallback_email
        if email:
            config.set_value("user", "email", email)
        config.set_value("user", "name", user.name)
        config.set_value("commit", "gpgsign", "false")

        return repo
