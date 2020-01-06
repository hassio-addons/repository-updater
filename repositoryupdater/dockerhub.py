#
# MIT License
#
# Copyright (c) 2018-2020 Franck Nijhof
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
DockerHub module.

Handles communication with Docker Hub.
"""

import urllib.request


class DockerHub:
    """This class represents Docker Hub."""

    @staticmethod
    def image_exists_on_dockerhub(name, version):
        """Check if give image and version exists on Docker Hub."""
        location = (
            f"https://registry.hub.docker.com/v2/repositories/{name}/tags/{version}/"
        )
        request = urllib.request.Request(location)
        request.get_method = lambda: "HEAD"

        try:
            urllib.request.urlopen(request)
            return True
        except urllib.request.HTTPError:
            return False
