#!/usr/bin/env bash
# Fast-forward or create the caller's version branch without rewriting history.
set -e
if git show-ref --verify --quiet "refs/remotes/origin/$VERSION"; then
  git fetch origin "$VERSION:refs/remotes/origin/$VERSION"
  git checkout -B "$VERSION" "origin/$VERSION"
  # Delayed runs are no-ops; divergence fails without rewriting history.
  if ! git merge --ff-only "$GITHUB_SHA"; then
    printf '%s%s\n' "::error::Version branch '$VERSION' has diverged from master. " \
      "Follow the documented manual recovery procedure." >&2
    exit 1
  fi
else
  # The normal push creates a missing remote version branch.
  git checkout -b "$VERSION" "$GITHUB_SHA"
fi
