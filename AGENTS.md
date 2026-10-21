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

| Path                     | Purpose                                                    |
| ------------------------ | ---------------------------------------------------------- |
| `src/repositoryupdater/` | The package                                                |
| `  cli.py`               | Click command and the Git askpass helper                   |
| `  repository.py`        | The apps repository: app list, README, commits and push    |
| `  app.py`               | One app: version resolution and the files an update writes |
| `  github.py`            | PyGithub subclass that can clone with the token            |
| `  output.py`            | Everything the terminal shows; nothing else prints         |
| `  exceptions.py`        | The `RepositoryUpdaterError` hierarchy                     |
| `  const.py`             | Channels and the file names that are looked up             |
| `tests/`                 | pytest suite with syrupy snapshots                         |
| `action.yaml`, `action/` | The GitHub Action                                          |
| `docker/`                | The container image                                        |

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
  through the `Output` instance they are handed.
- What an apps repository relies on is a contract: the `.apps.yml` format
  (including the `addons` key), the variables handed to `.README.j2`
  templates, the commit messages, the Action inputs and the `--addon` alias.
  Do not break them without a major release.
- Coverage is enforced at 85% for now. New code needs tests.
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

- `App` and `Repository` start with their state set to `None` and fill it in
  `load()`. ty cannot follow that, which is why `unresolved-attribute` is a
  warning and ty runs with `--exit-zero-on-warning`. Both go away with the
  planned async rewrite.
- A version that is valid semver is looked up as a Git tag, with or without a
  `v` prefix. Anything else is treated as a commit reference. On the edge
  channel, the version is the short SHA of the newest commit.
- prek hands pylint the files one by one, so `ignore = ["tests"]` does not keep
  it out of the tests. Test modules disable `redefined-outer-name` for pytest
  fixtures at the top of the file.
- coverage needs `source_pkgs`, not `source`: with the src layout a bare
  package name silently measures nothing.

## Where to read next

- `README.md`: the app list format, channels and the README templates.
- `tests/test_app.py`: how the latest version is picked on each channel.

[community-apps]: https://github.com/hassio-addons
[prek]: https://github.com/j178/prek
[uv]: https://docs.astral.sh/uv/
