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
Home Assistant add-ons repository updater setup
"""
from setuptools import setup, find_packages

from repositoryupdater import (
    __author__,
    __email__,
    __license__,
    __url__,
    __download__,
    APP_NAME,
    APP_VERSION,
    APP_DESCRIPTION,
)

setup(
    name=APP_NAME,
    version=APP_VERSION,
    author=__author__,
    author_email=__email__,
    description=APP_DESCRIPTION.split("\n")[0],
    long_description=APP_DESCRIPTION,
    license=__license__,
    url=__url__,
    download_url=__download__,
    keywords=[
        "addons",
        "repository",
        "home assistant",
        "home-assistant",
        "add-ons",
        "frenck",
    ],
    platforms="any",
    classifiers=[
        "Environment :: Console",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3 :: Only",
        "Topic :: Software Development :: Build Tools",
        "Topic :: Utilities",
    ],
    packages=find_packages(),
    install_requires=[
        "click==7.1.2",
        "crayons==0.4.0",
        "emoji==0.6.0",
        "GitPython==3.1.12",
        "Jinja2==2.11.2",
        "PyGithub==1.54.1",
        "python-dateutil==2.8.1",
        "PyYAML==5.3.1",
        "semver==2.13.0",
    ],
    entry_points="""
        [console_scripts]
            repository-updater=repositoryupdater.cli:repository_updater
            repository-updater-git-askpass=repositoryupdater.cli:git_askpass
    """,
)
