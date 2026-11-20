"""Prevent validation tokens from accidentally receiving organization-wide access."""

import os


def validate_repositories():
    if not os.environ.get("PUBLIC_VALIDATION_REPOSITORIES", ""):
        print("Error: PUBLIC_VALIDATION_REPOSITORIES environment variable is empty.")
        print("Failing to prevent minting a token with org-wide access.")
        return 1
    return 0
