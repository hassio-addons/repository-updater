# Contributing

Contributions are welcome. For anything bigger than a small fix, open an issue
first so we can align before you spend time on it.

Please follow the [code of conduct][code-of-conduct] in all your interactions
with the project.

AI tools are welcome as an aid, but you are responsible for everything you
submit: review and understand it before opening a pull request. Autonomous
agents are not allowed, and unreviewed AI output will be closed. Read the
[AI policy][ai-policy] before contributing.

## Issues and feature requests

Found a bug, a mistake in the documentation, or want a new feature? Open an
issue on the [GitHub repository][github]. Search the existing issues first,
your question may already be answered.

Found a security vulnerability? Do not open a public issue; follow the
[security policy][security] instead.

The output of a run with `--dry-run` helps a lot: it shows what the updater
found for every app and what it would commit, without changing anything.

## Development

This is a [uv][uv] project that also uses Node.js for Prettier, with
[prek][prek] running the checks. [AGENTS.md][agents] explains how the code is
laid out.

```bash
npm install
uv sync --group dev
uv run prek run --all-files   # lint, format, type, and test hooks
uv run pytest                 # just the tests
```

Every change is linted, type-checked, and tested in CI, which must be green
before a pull request can merge. Keep coverage up and match the surrounding
style (clear names, why-comments, no silent failures).

## Pull requests

1. Search for open or closed [pull requests][prs] that relate to yours, so you
   don't duplicate effort.
1. Keep the change focused and describe what it does and why.
1. Make sure tests cover your change and the full check suite passes locally.

[agents]: https://github.com/hassio-addons/repository-updater/blob/main/AGENTS.md
[ai-policy]: https://github.com/hassio-addons/repository-updater/blob/main/AI_POLICY.md
[code-of-conduct]: https://github.com/hassio-addons/repository-updater/blob/main/.github/CODE_OF_CONDUCT.md
[github]: https://github.com/hassio-addons/repository-updater/issues
[prek]: https://github.com/j178/prek
[prs]: https://github.com/hassio-addons/repository-updater/pulls
[security]: https://github.com/hassio-addons/repository-updater/blob/main/.github/SECURITY.md
[uv]: https://docs.astral.sh/uv/
