"""Check that dependency setup is optional during the CI rollout."""

from pathlib import Path

import yaml


def test_review_continues_without_a_ci_installer():
    workflow = (
        Path(__file__).resolve().parents[3] / "workflows/reusable-bot-ai-review.yml"
    )
    steps = yaml.safe_load(workflow.read_text())["jobs"]["review"]["steps"]
    by_name = {step.get("name"): step for step in steps}
    detect = by_name["Detect standardized CI"]
    assert detect["if"] == "${{ hashFiles('install-ci-deps.sh') != '' }}"
    select = by_name["Select CI environment"]
    assert select["if"] == "steps.ci-detect.outputs.enabled == 'true'"
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
    assert "'requirements-qa.txt'" in cache["with"]["key"]


def test_django_cache_includes_test_requirements():
    workflow = (
        Path(__file__).resolve().parents[3] / "workflows/reusable-bot-ai-review.yml"
    )
    steps = yaml.safe_load(workflow.read_text())["jobs"]["review"]["steps"]
    cache = next(step for step in steps if step.get("name") == "Restore Django cache")
    assert "'requirements-test.txt'" in cache["with"]["key"]


def test_review_services_start_after_setup_and_are_cleaned_up():
    workflow = (
        Path(__file__).resolve().parents[3] / "workflows/reusable-bot-ai-review.yml"
    )
    steps = yaml.safe_load(workflow.read_text())["jobs"]["review"]["steps"]
    by_name = {step.get("name"): step for step in steps}
    start = by_name["Start review services"]
    stop = by_name["Stop review services"]
    assert steps.index(start) > steps.index(by_name["Install trusted CI dependencies"])
    assert steps.index(stop) > steps.index(by_name["Run review"])
    assert start["env"]["DEFAULT_SHA"] == "${{ github.sha }}"
    assert "always()" in stop["if"]
