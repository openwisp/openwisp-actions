"""Read the caller's module version for the version branch workflow."""

import importlib
import os
import sys

# Running a file normally puts its own directory first, not the caller checkout.
sys.path.insert(0, os.getcwd())
version = importlib.import_module(os.environ["MODULE_NAME"]).VERSION
with open(os.environ["GITHUB_OUTPUT"], "a") as output:
    output.write(f"version={version[0]}.{version[1]}\n")
