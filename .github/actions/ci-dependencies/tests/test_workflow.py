"""Check that dependency setup is optional during the CI rollout."""

from pathlib import Path

import yaml


def test_review_continues_without_a_ci_installer():
    workflow = (
        Path(__file__).resolve().parents[3] / "workflows/reusable-bot-ai-review.yml"
    )
    steps = yaml.safe_load(workflow.read_text())["jobs"]["review"]["steps"]
    by_name = {step.get("name"): step for step in steps}
    select = by_name["Select CI environment"]
    assert select["if"] == "${{ hashFiles('install-ci-deps.sh') != '' }}"
    for name in ("Install OpenCode", "Run review", "Upload findings"):
        assert "if" not in by_name[name]
    assert by_name["Install trusted CI dependencies"]["if"] == (
        "steps.ci.outcome == 'success'"
    )


def test_python_cache_includes_runtime_requirements():
    workflow = (
        Path(__file__).resolve().parents[3] / "workflows/reusable-bot-ai-review.yml"
    )
    steps = yaml.safe_load(workflow.read_text())["jobs"]["review"]["steps"]
    cache = next(step for step in steps if step.get("name") == "Restore Python cache")
    assert "'requirements.txt'" in cache["with"]["key"]
