"""Prevent validation tokens from accidentally receiving organization-wide access."""

import os
import re


def validate_repositories():
    repositories = re.split(
        r"[,\n]+", os.environ.get("PUBLIC_VALIDATION_REPOSITORIES", "")
    )
    if not any(repository.strip() for repository in repositories):
        print("Error: PUBLIC_VALIDATION_REPOSITORIES environment variable is empty.")
        print("Failing to prevent minting a token with org-wide access.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(validate_repositories())
