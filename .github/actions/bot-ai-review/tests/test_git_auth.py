"""Check private Git authentication stays scoped to trusted review steps."""

import os
import subprocess
from pathlib import Path

import yaml

WORKFLOW = Path(__file__).resolve().parents[3] / "workflows/reusable-bot-ai-review.yml"


def test_private_git_auth_is_limited_to_fetch_steps(tmp_path):
    jobs = yaml.safe_load(WORKFLOW.read_text())["jobs"]
    review = jobs["review"]["steps"]
    publish = jobs["publish"]["steps"]
    for steps, name, token in (
        (review, "Fetch pull request as data", "${{ github.token }}"),
        (publish, "Fetch pull request for publication", "${{ github.token }}"),
    ):
        step = next(step for step in steps if step["name"] == name)
        env = step["env"]
        assert env["GH_TOKEN"] == token
        assert {key: env[key] for key in env if key.startswith("GIT_CONFIG_")} == {
            "GIT_CONFIG_COUNT": "2",
            "GIT_CONFIG_KEY_0": "credential.helper",
            "GIT_CONFIG_VALUE_0": "",
            "GIT_CONFIG_KEY_1": "credential.helper",
            "GIT_CONFIG_VALUE_1": "!gh auth git-credential",
        }
        fake_gh = tmp_path / "gh"
        fake_gh.write_text(
            '#!/bin/sh\nprintf "username=x-access-token\\npassword=%s\\n" "$GH_TOKEN"\n'
        )
        fake_gh.chmod(0o755)
        git_env = os.environ | {
            **{
                key: str(value)
                for key, value in env.items()
                if key.startswith("GIT_CONFIG_")
            },
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "HOME": str(tmp_path),
            "GH_TOKEN": "test-token",
        }
        result = subprocess.run(
            ["git", "credential", "fill"],
            input="protocol=https\nhost=github.com\n\n",
            env=git_env,
            text=True,
            capture_output=True,
            check=True,
        )
        assert "password=test-token" in result.stdout
        assert not (tmp_path / ".gitconfig").exists()
    write_token = next(
        step for step in publish if step["name"] == "Generate write app token"
    )
    assert "permission-contents" not in write_token["with"]
    fetch = next(
        step for step in publish if step["name"] == "Fetch pull request for publication"
    )
    assert fetch["run"] == 'git fetch --no-tags origin "refs/pull/$PR_NUMBER/head"'
    publish_step = next(step for step in publish if step["name"] == "Publish review")
    assert publish_step["env"]["GH_TOKEN"] == "${{ steps.app-token.outputs.token }}"
    assert not any(key.startswith("GIT_CONFIG_") for key in publish_step["env"])
    assert (
        next(step for step in review if step["name"] == "Run review")["env"].get(
            "GH_TOKEN"
        )
        is None
    )
