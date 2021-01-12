# Community Home Assistant Add-ons Repository Updater

[![PyPi Release][pypi-shield]][pypi]
[![GitHub Activity][commits-shield]][commits]
[![License][license-shield]](LICENSE.md)

![Project Stage][project-stage-shield]
![Project Maintenance][maintenance-shield]

[![Discord][discord-shield]][discord]
[![Community Forum][forum-shield]][forum]

## About

Reads remote add-on repositories, determines versions and generates
changelogs to update the add-on repository fully automated.

Mainly used by the Community Home Assistant Add-ons project.

Please note, this program cannot be used with the general documented
Home Assistant add-on repository approach and only works in the setup where
each add-on has its own GitHub repository.

## Installation

Using pip, the Python package manager:

```bash
pip install repository-updater
```

## Usage

The Repository Updater is a pretty simple, straightforward CLI tool.

```txt
Usage: repository-updater [OPTIONS]

  Community Home Assistant Add-ons Repository Updater.

Options:
  --token <TOKEN>                 GitHub access token
  --repository <orgname/reponame>
                                  The Home Assistant Addons repository to update
  --addon <TARGET>                Update a single/specific add-on
  --force                         Force an update of the add-on repository
  --version                       Show the version and exit.
  --help                          Show this message and exit.
```

To get a GitHub token, please see the GitHub article: [Create a token][token]

## Using Docker

The Repository Updater has been packaged in a Docker container as well.
This allows for easy and quick use, without the need for a Python setup. This
can be quite useful when using this tool in a CI server like; Travis,
CircleCI or GitLab CI.

```bash
docker run -it --rm hassioaddons/repository-updater:latest
```

All the usage information parameters from the previous chapter apply.
For example, this shows the current version of the tool:

```bash
docker run -it --rm hassioaddons/repository-updater:latest --version
```

## Add-ons Repository Configuration

In order for the Repository Updater to do its job, we need feed it some
information. It needs to know which add-ons there are currently in the
add-ons repository and where each add-on is located on GitHub.

Secondly, it needs to know the stability channel of the add-ons repository.
There are 3 stability channel levels available:

- **stable**: Stable releases
- **beta**: Beta / test releases
- **edge**: Latest builds, usually build straight from development

Create a `.addons.yml` file in the root of the add-ons repository,
which looks like this:

```yaml
channel: edge
addons:
  example:
    repository: hassio-addons/addon-example
    target: example
    image: hassioaddons/example-{arch}
  homebridge:
    repository: hassio-addons/addon-homebridge
    target: homebridge
    image: hassioaddons/homebridge-{arch}
  pihole:
    repository: hassio-addons/addon-pi-hole
    target: pi-hole
    image: hassioaddons/pi-hole-{arch}
```

The target in the add-ons repository is specified as the key for each add-on,
this will be the directory name inside the add-ons repository as well. This is
different from the `target` key, in a way that that key specified the add-on
target directory inside the git repository of the add-on itself.

In the above example, `pihole` will be the name of the add-on directory
inside the add-ons repository, while `pi-hole` is the directory in the add-on
git repo that contains the actual add-on.

`repository` specified the location of the add-on on GitHub. This must be
in `organization/repository` or `username/repository` format.

Finally, the `image` key defines the Docker container images on Docker Hub
for this add-on. `{arch}` can be used as a placeholder for the architecture and
is automatically replaced internally by the Repository Updater.

## Add-ons Repository README template

It is nice to have an up to date `README.md` file in your add-ons repository,
but maintaining one, can be quite time-consuming. The Repository updater is
able to update the `README.md` file for you each run.

This is done using a Jinja2 template. Simply create a file called `.README.j2`
in the root of your add-ons repository. Most information is collected
from the add-on `config.json` and GitHub repo.

The following variables are available in your templates and are passed into it
upon rendering your template.

- **addons**: A list of add-ons in this add-ons repository
- **channel**: The channel type of this add-ons repository
- **description**: The GitHub add-ons repository description
- **homepage**: The GitHub add-ons repository specified homepage URL
- **issues**: The URL to the issues listing of the GitHub add-ons repository
- **name**: The full GitHub name, e.g., `hassio-addons/repository`
- **repo**: The full URL to the GitHub add-ons repository

In the above variables, a list of `addons` was specified. Each item in this
list contains the following variables:

- **name**: Name of the add-on
- **description**: Description of the add-on
- **url**: URL of the add-on
- **repo**: URL to the add-on GitHub repo
- **archs**: List of supported architectures by this add-on
- **slug**: The add-on slug
- **target**: The target directory of the add-on inside the add-ons repository
- **image**: The (untouched) Docker Hub container image name
- **images**: Dictionary of images per architecture
  - **aarch64**: `aarch64` DockerHub image (if arch is supported)
  - **amd64**: `amd64` DockerHub image (if arch is supported)
  - **armhf**: `armhf` DockerHub image (if arch is supported)
  - **i386**: `i386` DockerHub image (if arch is supported)
- **version**: The version of the add-on
- **commit**: Full SHA of the commit bound to the current version
- **date**: Date and time of the above commit/version

## Examples

It is quite a complex setup to create an example for in this little document.
Nevertheless, see the [Community Home Assistant Addons Repository][repository]
for an example of `.README.j2` and `.addons.yml` files.

The community project also uses GitLab for building its add-ons. Each
add-on runs this tool upon build, ensuring the repositories are always up to
date. Be sure to check some of the add-ons out as well to learn more about
the whole setup.

## Why do this all

Let me start by saying, there is nothing wrong with the documented way of
setting up a Home Assistant add-ons repository. If you are just starting out
developing add-ons, please use the official documented way. You can always
decide to change your workflow.

Nevertheless, there are some advantages using the alternative method:

- Each add-on has its own Git repository, which allows for a maximum separation
  of concerns. Each add-on has its own issue list, releases, and all other
  GitHub goodness.
- Release and versioning is based on GitHub Releases / Git tagging. Which
  does not need updating of configuration files and is done with a single click.
- Each add-on Git repository is downloadable and instantly buildable locally.
- Every single piece of manual labor around maintaining an add-ons repository
  is fully automated. Building, testing, quality control, publishing, changelogs
  and even the add-ons repository README are updated automatically.  This level
  of automation allows us to focus completely on developing the actual add-on.
- Availability of Beta and Edge channels for everyone who's interested or
  willing to test.

## Known issues and limitations

- Any kind of testing and linting... is missing...

## Changelog & Releases

This repository keeps a change log using [GitHub's releases][releases]
functionality. The format of the log is based on
[Keep a Changelog][keepchangelog].

Releases are based on [Semantic Versioning][semver], and use the format
of ``MAJOR.MINOR.PATCH``. In a nutshell, the version will be incremented
based on the following:

- ``MAJOR``: Incompatible or major changes.
- ``MINOR``: Backwards-compatible new features and enhancements.
- ``PATCH``: Backwards-compatible bugfixes and package updates.

## Support

Got questions?

You have several options to get them answered:

- The Home Assistant [Community Forum][forum].
- The Home Assistant [Discord Chat Server][discord] for general Home Assistant
  discussions and questions.
- Join the [Reddit subreddit][reddit] in [/r/homeassistant][reddit]

You could also [open an issue here][issue] GitHub.

## Contributing

This is an active open-source project. We are always open to people who want to
use the code or contribute to it.

We have set up a separate document containing our
[contribution guidelines](CONTRIBUTING.md).

Thank you for being involved! :heart_eyes:

## Authors & contributors

The original setup of this repository is by [Franck Nijhof][frenck].

For a full list of all authors and contributors,
check [the contributor's page][contributors].

## We have got some Home Assistant add-ons for you

Want some more functionality to your Home Assistant instance?

We have created multiple add-ons for Home Assistant. For a full list, check out
our [GitHub Repository][repository].

## License

MIT License

Copyright (c) 2018-2021 Franck Nijhof

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

[commits-shield]: https://img.shields.io/github/commit-activity/y/hassio-addons/repository-updater.svg
[commits]: https://github.com/hassio-addons/repository-updater/commits/master
[contributors]: https://github.com/hassio-addons/repository-updater/graphs/contributors
[discord-shield]: https://img.shields.io/discord/330944238910963714.svg
[discord]: https://discord.gg/c5DvZ4e
[forum-shield]: https://img.shields.io/badge/community-forum-brightgreen.svg
[forum]: https://community.home-assistant.io?u=frenck
[frenck]: https://github.com/frenck
[issue]: https://github.com/hassio-addons/repository-updater/issues
[keepchangelog]: http://keepachangelog.com/en/1.0.0/
[license-shield]: https://img.shields.io/github/license/hassio-addons/repository-updater.svg
[maintenance-shield]: https://img.shields.io/maintenance/yes/2021.svg
[project-stage-shield]: https://img.shields.io/badge/project%20stage-experimental-yellow.svg
[pypi-shield]: https://img.shields.io/pypi/v/repository-updater.svg
[pypi]: https://pypi.org/project/repository-updater
[reddit]: https://reddit.com/r/homeassistant
[releases]: https://github.com/hassio-addons/repository-updater/releases
[repository]: https://github.com/hassio-addons/repository
[semver]: http://semver.org/spec/v2.0.0.html
[token]: https://help.github.com/articles/creating-a-personal-access-token-for-the-command-line/
