"""
PyGithub wrapper that can clone with the token.

On its way out: the asynchronous client in the github package replaces it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from git import Repo
from github import Github as PyGitHub

if TYPE_CHECKING:
    from github.Repository import Repository


class GitHub(PyGitHub):
    """Object for communicating with GitHub and cloning repositories."""

    token: str

    def __init__(self, token: str) -> None:
        """Initialize a new GitHub object."""
        super().__init__(login_or_token=token)
        self.token = token

    def clone(self, repository: Repository, destination: str) -> Repo:
        """Clone a GitHub repository and return a Git object."""
        environ = {
            "GIT_ASKPASS": "repository-updater-git-askpass",
            "GIT_USERNAME": self.token,
            "GIT_PASSWORD": "",
        }

        repo = Repo.clone_from(repository.clone_url, destination, None, environ)

        config = repo.config_writer()
        if self.get_user().email:
            config.set_value("user", "email", self.get_user().email)
        config.set_value("user", "name", self.get_user().name)
        config.set_value("commit", "gpgsign", "false")

        return repo
