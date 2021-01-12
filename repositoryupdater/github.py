#
# MIT License
#
# Copyright (c) 2018-2021 Franck Nijhof
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

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
