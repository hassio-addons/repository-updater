# GitHub API fixtures

Real answers from the GitHub REST API (version 2022-11-28), recorded without a
token so they hold public data only. `user.json` is GitHub's own demo account,
`octocat`.

The answers to writes (`git_*_created.json`, `git_ref_updated.json`) and the
rate limit and permission errors follow the examples in the GitHub REST API
documentation, since recording them means writing to a repository.

To re-record a read, for example:

```bash
curl -sS -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  https://api.github.com/repos/hassio-addons/app-ssh > repository.json
```
