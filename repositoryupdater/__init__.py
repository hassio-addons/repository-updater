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
Community Home Assistant Add-ons Repository Updater.

Reads remote add-on repositories, determines versions and generates
changelogs to update the add-on repository fully automated.

Mainly used by the Community Home Assistant Add-ons project.

Please note, this program cannot be used with the general documented
Home Assistant add-on repository approach.
"""


APP_NAME = "repository-updater"
APP_FULL_NAME = "Community Home Assistant Add-ons Repository Updater"
APP_VERSION = "0.6.0"
APP_DESCRIPTION = __doc__

__author__ = "Franck Nijhof"
__email__ = "frenck@addons.community"
__copyright__ = "Copyright 2018-2021, Franck Nijhof"
__license__ = "MIT"
__url__ = "https://github.com/hassio-addons/repository-updater"
__download__ = (
    "https://github.com/hassio-addons/repository-updater/archive/0.6.0.tar.gz"
)
__version__ = APP_VERSION
