"""Check for standard CI entry points on the pull request's trusted base."""

import json
import os
import subprocess
import sys

CI_WORKFLOW = ".github/workflows/ci.yml"
INSTALLER = "install-ci-deps.sh"


def tree(repository, sha):
    output = subprocess.check_output(
        ["gh", "api", f"repos/{repository}/git/trees/{sha}"], text=True
    )
    data = json.loads(output)
    if data.get("truncated"):
        raise ValueError("GitHub returned an incomplete tree")
    return data


def entry(data, name, kind):
    return next(
        (
            item
            for item in data["tree"]
            if item["path"] == name and item["type"] == kind
        ),
        None,
    )


def check(repository, base_sha):
    # Read only the three small trees needed. PR files are untrusted and may
    # claim that the base branch has already adopted the convention.
    root = tree(repository, base_sha)
    installer = entry(root, INSTALLER, "blob")
    github = entry(root, ".github", "tree")
    workflows = None
    if github:
        workflows = entry(tree(repository, github["sha"]), "workflows", "tree")
    workflow = None
    if workflows:
        workflow = entry(tree(repository, workflows["sha"]), "ci.yml", "blob")
    missing = []
    if not workflow:
        missing.append(CI_WORKFLOW)
    if not installer:
        missing.append(INSTALLER)
    return missing


def main():
    try:
        missing = check(os.environ["REPOSITORY"], os.environ["BASE_SHA"])
    except (
        subprocess.SubprocessError,
        ValueError,
        KeyError,
        json.JSONDecodeError,
    ) as error:
        # An API failure is not evidence that the repository lacks a file.
        print(f"::warning::Could not check CI entry points: {error}", file=sys.stderr)
        status, missing = "unknown", []
    else:
        status = "missing" if missing else "present"
    with open(os.environ["GITHUB_OUTPUT"], "a") as output:
        output.write(f"status={status}\nmissing={', '.join(missing)}\n")


if __name__ == "__main__":
    main()
