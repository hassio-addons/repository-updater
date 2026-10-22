# AGENTS.md

Guidance for AI coding agents (and humans) working in this repository. This file
follows the [agents.md](https://agents.md) convention. `CLAUDE.md` is a symlink
to this file, so Claude-compatible tooling reads the same guidance.

## What this project is

The repository updater keeps a Home Assistant apps repository in sync with the
Git repositories of the apps it lists. For every app it finds the latest
version the repository's channel may publish (stable, beta or edge), copies
the app's configuration, static files and changelog into the apps repository,
re-renders the READMEs from their templates, commits and pushes. It powers the
[Home Assistant Community Apps][community-apps] project, and runs as a CLI, a
container image and a GitHub Action.

The apps repository declares its apps in `.apps.yml` (or the older
`.addons.yml` and `.hassio-addons.yml`). See `README.md` for the format.

## Project layout

| Path                     | Purpose                                                |
| ------------------------ | ------------------------------------------------------ |
| `src/repositoryupdater/` | The package                                            |
| `  cli/`                 | Typer command and its error handling; runs the updater |
| `  updater.py`           | Loads every app and commits the updates                |
| `  github/`              | Asynchronous client for the GitHub API we use          |
| `  applist.py`           | The `.apps.yml` model                                  |
| `  versions.py`          | Which version a channel publishes, and how it shows    |
| `  appconfig.py`         | Reading and writing app configuration files            |
| `  render.py`            | READMEs, changelogs and commit messages                |
| `  archive.py`           | Reading app files out of a repository tarball          |
| `  cache.py`             | What a run remembers of an apps repository             |
| `  output.py`            | Everything the terminal shows; nothing else prints     |
| `  exceptions.py`        | The `RepositoryUpdaterError` hierarchy                 |
| `  const.py`             | Channels and the file names that are looked up         |
| `tests/`                 | pytest suite with syrupy snapshots                     |
| `action.yaml`            | The GitHub Action; runs the published image            |
| `Dockerfile`             | The container image, built from the wheel              |

## Commands

This is a [uv][uv] project that also uses Node.js for Prettier, with
[prek][prek] running the hooks. Set up and run the gate with:

```bash
npm install
uv sync --group dev
uv run prek run --all-files   # lint, format, type, and test hooks
uv run pytest                 # just the tests
```

During iteration, running a single tool directly is fine and faster:
`uv run pytest -k ...`, `uv run ruff check .`, `uv run ty check`. Update
snapshots with `uv run pytest --snapshot-update` and review the diff before
committing it.

## Conventions

- Failures the user can act on raise a subclass of `RepositoryUpdaterError`.
  The CLI turns those into a clean error message; anything else is a bug.
- Only `output.py` writes to the terminal. Other modules report what happened
  through the `Output` instance they are handed. Messages are Rich markup, so
  values from the outside go through `plain()`, `highlight()` or `emphasis()`.
  On GitHub Actions, sections become log groups and errors annotations.
- What an apps repository relies on is a contract: the `.apps.yml` format
  (including the `addons` key), the variables handed to `.README.j2`
  templates, the commit messages, the Action inputs and the `--addon` alias.
  Do not break them without a major release.
- Coverage is enforced at 95%. New code needs tests.
- Every test carries a one-line docstring describing what it verifies.
- Comments explain the why, not the what. Clarity over cleverness, clear names,
  and blank lines between logical steps.

## Writing and voice

English for all public artifacts (commits, PRs, issues). Held to a high bar:
clear, honest, no filler. Avoid:

- AI cheerleading and marketing speak (leverage, synergize, delight).
- Em-dashes and en-dashes anywhere. Use a period, colon, comma, or parentheses;
  hyphen only for compound words. Restructure a sentence rather than reach for one.
- "e.g.", "i.e.", "etc."; write "like", "for example", "such as".
- CAPS for emphasis (use italics); "click" as a verb (use "select").
- "HA"/"HASS"; write "Home Assistant" in full, and never frame it as fragile.
- "master/slave"; use "client/server", "leader/follower", "main/replica".

See [AI_POLICY.md](AI_POLICY.md) for the contribution policy around AI tooling.

## Gotchas

- A published version is looked up as a Git ref: first as is, then with a
  `v` in front. That covers both tag styles and the short SHA an edge version
  is. Whether a README shows it with a `v` depends on whether it is the start
  of its commit SHA, not on what the version looks like.
- Prereleases are recognized with AwesomeVersion, the way Home Assistant reads
  versions. Only real version numbers can be one; a SHA never is.
- The updater never clones. It reads files and tarballs through the API and
  commits through the Git Data API, one commit per app.
- The cache holds what the apps repository has of each app, so a run for one
  app skips loading the rest. An entry only counts when the blob SHA of the
  app's configuration still matches the tree of the apps repository; after a
  commit the updater works out the new SHA itself. A broken cache only makes a
  run slower. It does keep an app's repository URL and commit until that
  configuration changes. Bump `CACHE_VERSION` when what it holds changes.
- A run works from the head of the branch it read at the start, and every
  commit only goes on top of that head (moving along with its own commits).
  When the branch moved under it, the run stops: what it would commit was
  worked out from the old state and could undo the other change.
- README templates come from app repositories, so they render in a Jinja
  sandbox and never see the process, its environment or the token.
- `--dry-run` compares what would be committed with what is there, without
  writing. A forced dry run (`--force --dry-run`) against a real apps
  repository should show nothing but updates that are actually waiting.
- prek hands pylint the files one by one, so `ignore = ["tests"]` does not keep
  it out of the tests. Test modules disable `redefined-outer-name` for pytest
  fixtures at the top of the file.
- coverage needs `source_pkgs`, not `source`: with the src layout a bare
  package name silently measures nothing.

## Releasing

Releases are immutable: once published, a release and its tag never change.
So nothing gets published by hand. Release-drafter keeps a draft with the
next version; the release pull request points `action.yaml` at that version
(`docker://ghcr.io/hassio-addons/repository-updater:<version>`). Then the
Release workflow, started with "Run workflow" on `main`:

1. checks that every workflow run on that commit passed, that there is one
   draft whose tag does not exist yet, and that `action.yaml` points at it;
2. builds the package;
3. pushes the image to GHCR, so the release never points at a missing one;
4. publishes the draft, with its tag on that very commit;
5. publishes the package to PyPI.

A job that fails after the release is published can simply be re-run. Every
tag is an exact version; nothing like `v3` or `latest` moves along.

## Where to read next

- `README.md`: the app list format, channels and the README templates.
- `tests/test_versions.py`: how the version a channel publishes is picked.
- `tests/test_updater.py`: whole runs against a GitHub in memory.

[community-apps]: https://github.com/hassio-addons
[prek]: https://github.com/j178/prek
[uv]: https://docs.astral.sh/uv/
