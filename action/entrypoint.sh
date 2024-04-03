#!/usr/bin/env bash
declare -a options

options+=(--token "${INPUT_TOKEN:-}")

if [[ -n "${INPUT_REPOSITORY:-}" ]]; then
  options+=(--repository "${INPUT_REPOSITORY}")
else
  options+=(--repository "${GITHUB_REPOSITORY}")
fi

[[ -n "${INPUT_ADDON:-}" ]] \
  && options+=(--addon "${INPUT_ADDON}")

[[ "${INPUT_FORCE,,}" = "true" ]] \
  && options+=(--force)

if [[ -n "${GITHUB_ACTOR:-}" ]]; then
  options+=(--git-name "${GITHUB_ACTOR}")
  git config --global user.name "${GITHUB_ACTOR}"

if [[ -n "${GITHUB_ACTOR_ID:-}" ]]; then
  options+=(--git-email "${GITHUB_ACTOR_ID}+${GITHUB_ACTOR}@users.noreply.github.com")
  git config --global user.email "${GITHUB_ACTOR_ID}+${GITHUB_ACTOR}@users.noreply.github.com"

# Output version
repository-updater --version

# Update!
exec repository-updater "${options[@]}"
