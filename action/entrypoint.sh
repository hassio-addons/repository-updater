#!/usr/bin/env bash
declare -a options

options+=(--token "${INPUT_TOKEN:-}")

if [[ -n "${INPUT_REPOSITORY:-}" ]]; then
  options+=(--repository "${INPUT_REPOSITORY}")
else
  options+=(--repository "${GITHUB_REPOSITORY}")
fi

# Support both 'app' (new) and 'addon' (deprecated) inputs
# Prefer 'app' if both are provided
if [[ -n "${INPUT_APP:-}" ]]; then
  options+=(--app "${INPUT_APP}")
elif [[ -n "${INPUT_ADDON:-}" ]]; then
  options+=(--app "${INPUT_ADDON}")
fi

[[ "${INPUT_FORCE,,}" = "true" ]] \
  && options+=(--force)

# Output version
repository-updater --version

# Update!
exec repository-updater "${options[@]}"
