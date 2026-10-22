# Home Assistant Community Apps Repository Updater

[![PyPI Release][pypi-shield]][pypi]
[![Python Versions][python-versions-shield]][pypi]
![Project Stage][project-stage-shield]
![Project Maintenance][maintenance-shield]
[![License][license-shield]](LICENSE.md)

[![Build Status][build-shield]][build]
[![Code Coverage][codecov-shield]][codecov]
[![OpenSSF Scorecard][scorecard-shield]][scorecard]

[![Discord][discord-shield]][discord]
[![Community Forum][forum-shield]][forum]

## About

Keeps a Home Assistant apps repository up to date with the apps it lists,
fully automated. For every app, it finds the newest version the repository's
channel may publish, copies the app's configuration, static files and
changelog into the apps repository, renders the READMEs from their templates,
and commits the result. One commit per app, straight through the GitHub API,
without cloning anything.

It powers the [Home Assistant Community Apps][repository] project, and runs as
a command line tool, a container image and a GitHub Action.

Please note, this program cannot be used with the general documented
Home Assistant app repository approach and only works in the setup where
each app has its own GitHub repository.

## Installation

The Repository Updater needs Python 3.12 or newer. Install it with pip, or
run it straight away with [uv][uv]:

```bash
pip install repository-updater
uvx repository-updater --help
```

It is also available as a container image and as a GitHub Action, see below.

### The token

The Repository Updater needs a GitHub token that may commit to the apps
repository. A fine-grained personal access token needs read and write access
to the contents of the apps repository; a classic one needs the `repo` scope.
Public app repositories need nothing extra; private ones need read access to
their contents as well. To get a token, see the GitHub article:
[Create a token][token].

The commits are made in the name of the account the token belongs to. When
that account keeps its email address private, the commits use its GitHub
noreply address.

## Usage

The Repository Updater is a pretty simple, straightforward CLI tool.

```txt
 Usage: repository-updater [OPTIONS]

 Bring a Home Assistant Apps repository up to date with its apps.

╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ *  --token                        TOKEN       GitHub access token.                               │
│                                               [env var: INPUT_TOKEN, GITHUB_TOKEN]               │
│                                               [required]                                         │
│ *  --repository                   OWNER/NAME  The Home Assistant Apps repository to update.      │
│                                               [env var: INPUT_REPOSITORY, GITHUB_REPOSITORY]     │
│                                               [required]                                         │
│    --app,--addon                  APP         Update a single app. --addon is the deprecated     │
│                                               name.                                              │
│                                               [env var: INPUT_APP, INPUT_ADDON]                  │
│    --force                                    Update apps even when they look up to date.        │
│                                               [env var: INPUT_FORCE]                             │
│    --dry-run                                  Show what would be committed, without committing.  │
│                                               [env var: INPUT_DRY_RUN]                           │
│    --cache          --no-cache                Remember what the apps repository holds, to skip   │
│                                               reloading it.                                      │
│                                               [env var: INPUT_CACHE]                             │
│                                               [default: cache]                                   │
│    --cache-dir                    PATH        Where the cache lives. Defaults to                 │
│                                               ~/.cache/repository-updater.                       │
│                                               [env var: INPUT_CACHE_DIR]                         │
│    --version                                  Show the version and exit.                         │
│    --help                                     Show this message and exit.                        │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

Every option can also be set through the environment variables listed with
it. When more than one is set, the first one that is not empty wins, and an
option on the command line always beats the environment. `--addon` and the
`INPUT_ADDON` variable are deprecated; use `--app` and `INPUT_APP` instead.

### The cache

A run for a single app still needs every other app, to render the README of
the apps repository. The Repository Updater remembers what the apps repository
holds of each app in a cache, so the next run only loads what changed. Every
cached app is checked against the apps repository first: an app that changed
since, even by hand, simply gets loaded again. The cache lives in
`~/.cache/repository-updater` (or `$XDG_CACHE_HOME`); `--cache-dir` puts it
elsewhere and `--no-cache` runs without it.

## Using Docker

The Repository Updater is also published as a container image on the GitHub
Container Registry, for amd64 and arm64. This allows for quick use without a
Python setup, for example on a CI server.

```bash
docker run --rm -e GITHUB_TOKEN ghcr.io/hassio-addons/repository-updater:latest \
  --repository hassio-addons/repository
```

All the options from the previous chapter apply, including their
environment variables. For example, this shows the current version:

```bash
docker run --rm ghcr.io/hassio-addons/repository-updater:latest --version
```

Every image is signed with [cosign][cosign] and carries a build provenance
attestation, which can be checked with:

```bash
gh attestation verify --owner hassio-addons \
  oci://ghcr.io/hassio-addons/repository-updater:latest
```

## Using a GitHub Action

The Repository Updater is also available as a GitHub Action.

```yaml
---
name: Repository Update

on:
  repository_dispatch:
    types: ["update"]

jobs:
  whatever:
    name: Running updater for ${{ github.event.client_payload.app }}
    runs-on: ubuntu-latest
    steps:
      - name: 🚀 Run Repository Updater
        uses: hassio-addons/repository-updater@v2
        with:
          app: ${{ github.event.client_payload.app }}
          repository: ${{ github.repository }}
          token: ${{ secrets.UPDATER_TOKEN }}
```

The action takes these inputs:

| Input        | Default                   | What it does                                                   |
| ------------ | ------------------------- | -------------------------------------------------------------- |
| `token`      |                           | GitHub token that may commit to the apps repository. Required. |
| `repository` | The repository it runs in | The apps repository to update.                                 |
| `app`        |                           | Update a single app. `addon` is the deprecated name for it.    |
| `force`      | `false`                   | Update apps even when they look up to date.                    |
| `dry_run`    | `false`                   | Show what would be committed, without committing.              |
| `cache`      | `true`                    | Keep the cache between runs with `actions/cache`.              |

Every app gets its own group in the log, and an app that fails shows up as an
error annotation on the run, while the other apps carry on.

Once that workflow is in place, from an app repository, you can trigger
the above workflow to run. This can be done by dispatching a signal to
the updater workflow:

```yaml
publish:
  name: 📢 Publish App
  runs-on: ubuntu-latest
  steps:
    - name: 🚀 Dispatch Repository Updater update signal
      uses: peter-evans/repository-dispatch@v1
      with:
        token: ${{ secrets.DISPATCH_TOKEN }}
        repository: hassio-addons/repository
        event-type: update
        client-payload: '{"app": "my-app"}'
```

## Apps Repository Configuration

In order for the Repository Updater to do its job, we need feed it some
information. It needs to know which apps there are currently in the
apps repository and where each app is located on GitHub.

Secondly, it needs to know the stability channel of the apps repository.
There are 3 stability channel levels available:

- **stable**: Stable releases
- **beta**: Beta / test releases
- **edge**: Latest builds, usually build straight from development

Create a `.apps.yml` file in the root of the apps repository,
which looks like this:

```yaml
channel: edge
apps:
  example:
    repository: hassio-addons/app-example
    target: example
    image: ghcr.io/hassio-addons/example
  another:
    repository: hassio-addons/app-another
    target: homebridge
    image: ghcr.io/hassio-addons/another
  demo:
    repository: hassio-addons/app-demo
    target: src
    image: ghcr.io/hassio-addons/demo/{arch}
```

Older apps repositories call this file `.addons.yml` or `.hassio-addons.yml`,
and the `apps` key `addons`; both still work.

The target in the apps repository is specified as the key for each app,
this will be the directory name inside the apps repository as well. This is
different from the `target` key, in a way that that key specified the app
target directory inside the git repository of the app itself.

In the above example, `demo` will be the name of the app directory
inside the apps repository, while `src` is the directory in the app
git repo that contains the actual app.

`repository` specified the location of the app on GitHub. This must be
in `organization/repository` or `username/repository` format.

Finally, the `image` key defines the container image of this app, on the
GitHub Container Registry or any other registry. For an image per
architecture, `{arch}` is the placeholder for the architecture; a
multi-architecture image needs none.

By default, each release replaces the app's `CHANGELOG.md` with its release
notes. Set `changelog: prepend` at the top level of `.apps.yml` to keep the
earlier entries instead:

```yaml
channel: stable
changelog: prepend
apps: ...
```

Each release then adds its notes under a `## <version>` heading above the
newest version in `CHANGELOG.md`. A title like `# Changelog` and any
introduction stay on top. When an apps repository switches from `replace`, the
release notes already in `CHANGELOG.md` get a heading with the version they
belong to. Home Assistant uses these headings to show the changes between the
installed and the new version. Edge updates without a release still replace the
file.

## Apps Repository README template

It is nice to have an up to date `README.md` file in your apps repository,
but maintaining one, can be quite time-consuming. The Repository updater is
able to update the `README.md` file for you each run.

This is done using a Jinja2 template. Simply create a file called `.README.j2`
in the root of your apps repository. Most information is collected
from the configuration file of each app (`config.yaml`, `config.yml` or
`config.json`) and its GitHub repository. An app can have a `.README.j2` of
its own as well, which gets the variables of that one app.

The following variables are available in your templates and are passed into it
upon rendering your template.

- **apps**: A list of apps in this apps repository
- **addons**: Alias for `apps` (for backward compatibility)
- **channel**: The channel type of this apps repository
- **description**: The GitHub apps repository description
- **homepage**: The GitHub apps repository specified homepage URL
- **issues**: The URL to the issues listing of the GitHub apps repository
- **name**: The full GitHub name, like `hassio-addons/repository`
- **repo**: The full URL to the GitHub apps repository

In the above variables, a list of `apps` was specified. Each item in this
list contains the following variables:

- **name**: Name of the app
- **description**: Description of the app
- **url**: URL of the app
- **repo**: URL to the app GitHub repo
- **repo_slug**: app GitHub slug (:user/:repo)
- **archs**: List of supported architectures by this app
- **slug**: The app slug
- **target**: The target directory of the app inside the apps repository
- **image**: The container image, as written in `.apps.yml`
- **images**: Dictionary of images per architecture
  - **aarch64**: `aarch64` image (if the app supports it)
  - **amd64**: `amd64` image (if the app supports it)
- **channel**: The channel of the apps repository
- **version**: The version of the app, like `v1.2.3` for a release, or the
  short SHA of a commit on edge
- **commit**: Full SHA of the commit bound to the current version
- **date**: Date and time of the release, or of the commit on edge

## Examples

It is quite a complex setup to create an example for in this little document.
Nevertheless, see the [Home Assistant Community Apps Repository][repository]
for an example of `.README.j2` and `.apps.yml` files.

The community project runs the Repository Updater from GitHub Actions. When
an app gets a release, or a new commit on edge, its repository sends an
`update` event to the apps repositories, whose workflow runs this action for
that one app. See the [shared workflows][workflows] for the whole setup.

## Why do this all

Let me start by saying, there is nothing wrong with the documented way of
setting up a Home Assistant apps repository. If you are just starting out
developing apps, please use the official documented way. You can always
decide to change your workflow.

Nevertheless, there are some advantages using the alternative method:

- Each app has its own Git repository, which allows for a maximum separation
  of concerns. Each app has its own issue list, releases, and all other
  GitHub goodness.
- Release and versioning is based on GitHub Releases / Git tagging. Which
  does not need updating of configuration files and is done in one go.
- Each app Git repository is downloadable and instantly buildable locally.
- Every single piece of manual labor around maintaining an apps repository
  is fully automated. Building, testing, quality control, publishing, changelogs
  and even the apps repository README are updated automatically. This level
  of automation allows us to focus completely on developing the actual app.
- Availability of Beta and Edge channels for everyone who's interested or
  willing to test.

## Known issues and limitations

- It only works with apps repositories and app repositories on GitHub.
- A README template renders from a single file; `{% include %}` of other
  files in the repository is not available.

## Development

This is a [uv][uv] project that also uses Node.js for Prettier, with
[prek][prek] running the checks. Set up and run everything with:

```bash
npm install
uv sync --group dev
uv run prek run --all-files
```

`uv run pytest` runs just the tests. `--dry-run`, together with `--force`,
shows what a run would change in a real apps repository without writing
anything. [AGENTS.md](AGENTS.md) has more on how the code is laid out.

## Changelog & Releases

This repository keeps a change log using [GitHub's releases][releases]
functionality.

Releases are based on [Semantic Versioning][semver], and use the format
of `MAJOR.MINOR.PATCH`. In a nutshell, the version will be incremented
based on the following:

- `MAJOR`: Incompatible or major changes.
- `MINOR`: Backwards-compatible new features and enhancements.
- `PATCH`: Backwards-compatible bugfixes and package updates.

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
[contribution guidelines](.github/CONTRIBUTING.md).

Thank you for being involved! :heart_eyes:

## Authors & contributors

The original setup of this repository is by [Franck Nijhof][frenck].

For a full list of all authors and contributors,
check [the contributor's page][contributors].

## We have got some Home Assistant apps for you

Want some more functionality to your Home Assistant instance?

We have created multiple apps for Home Assistant. For a full list, check out
our [GitHub Repository][repository].

## License

MIT License

Copyright (c) 2018-2026 Franck Nijhof

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

[build-shield]: https://github.com/hassio-addons/repository-updater/actions/workflows/tests.yaml/badge.svg
[build]: https://github.com/hassio-addons/repository-updater/actions/workflows/tests.yaml
[codecov-shield]: https://codecov.io/gh/hassio-addons/repository-updater/branch/main/graph/badge.svg
[codecov]: https://codecov.io/gh/hassio-addons/repository-updater
[contributors]: https://github.com/hassio-addons/repository-updater/graphs/contributors
[cosign]: https://docs.sigstore.dev/cosign/
[discord-shield]: https://img.shields.io/discord/330944238910963714.svg
[discord]: https://discord.gg/c5DvZ4e
[forum-shield]: https://img.shields.io/badge/community-forum-brightgreen.svg
[forum]: https://community.home-assistant.io?u=frenck
[frenck]: https://github.com/frenck
[issue]: https://github.com/hassio-addons/repository-updater/issues
[license-shield]: https://img.shields.io/github/license/hassio-addons/repository-updater.svg
[maintenance-shield]: https://img.shields.io/maintenance/yes/2026.svg
[project-stage-shield]: https://img.shields.io/badge/project%20stage-production%20ready-brightgreen.svg
[pypi-shield]: https://img.shields.io/pypi/v/repository-updater.svg
[pypi]: https://pypi.org/project/repository-updater
[python-versions-shield]: https://img.shields.io/pypi/pyversions/repository-updater
[prek]: https://github.com/j178/prek
[reddit]: https://reddit.com/r/homeassistant
[releases]: https://github.com/hassio-addons/repository-updater/releases
[repository]: https://github.com/hassio-addons/repository
[scorecard-shield]: https://api.scorecard.dev/projects/github.com/hassio-addons/repository-updater/badge
[scorecard]: https://scorecard.dev/viewer/?uri=github.com/hassio-addons/repository-updater
[semver]: http://semver.org/spec/v2.0.0.html
[token]: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens
[uv]: https://docs.astral.sh/uv/
[workflows]: https://github.com/hassio-addons/workflows
