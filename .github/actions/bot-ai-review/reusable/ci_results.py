"""Identify the CI run belonging to a pull request revision."""

import json
import os
import subprocess
import tempfile
from pathlib import Path


class AmbiguousCIError(ValueError):
    """The available run data cannot identify one pull request safely."""


def matching_runs(runs, pr):
    matches = []
    head = pr["head"]
    for run in runs:
        if run["event"] != "pull_request" or run["head_sha"] != head["sha"]:
            continue
        pull_requests = run.get("pull_requests") or []
        if pull_requests:
            if len(pull_requests) != 1 or pull_requests[0]["number"] != pr["number"]:
                continue
        else:
            # GitHub can omit pull request associations for forked pull requests.
            if (
                not head.get("repo")
                or not run.get("head_repository")
                or run["head_repository"]["id"] != head["repo"]["id"]
                or run["head_branch"] != head["ref"]
            ):
                continue
        matches.append(run)
    return matches


def classify(run):
    if run["status"] != "completed":
        return "waiting"
    if run.get("conclusion") in ("success", "failure"):
        return "ready"
    return "stopped"


def select_run(runs, pr):
    # A newer run for the same PR and SHA supersedes an older run. Retries of
    # the same run are represented by its current attempt rather than a new ID.
    for run in runs:
        associations = run.get("pull_requests") or []
        if (
            run["event"] == "pull_request"
            and run["head_sha"] == pr["head"]["sha"]
            and len(associations) > 1
            and any(item["number"] == pr["number"] for item in associations)
        ):
            raise AmbiguousCIError("CI run is associated with multiple pull requests")
    return max(matching_runs(runs, pr), key=lambda run: run["id"], default=None)


def gh(endpoint):
    output = subprocess.check_output(["gh", "api", "--paginate", endpoint], text=True)
    # gh prints each page as a separate JSON document; decode all pages rather
    # than assuming that the response fits in one page.
    decoder = json.JSONDecoder()
    pages = []
    remaining = output.strip()
    while remaining:
        page, end = decoder.raw_decode(remaining)
        pages.append(page)
        remaining = remaining[end:].lstrip()
    return pages


def failed_logs(repository, run_id, attempt):
    script = (
        Path(__file__).resolve().parents[2] / "bot-ci-failure/reusable/fetch_logs.sh"
    )
    env = {
        **os.environ,
        "REPO": repository,
        "RUN_ID": str(run_id),
        "ATTEMPT": str(attempt),
        "MAX_LOG_BYTES": "65536",
    }
    with tempfile.TemporaryDirectory() as directory:
        result = subprocess.run(
            ["bash", str(script)], cwd=directory, env=env, capture_output=True
        )
        path = Path(directory) / "failed_logs.txt"
        if result.returncode != 0 or not path.is_file():
            return "Failed-job logs unavailable."
        return path.read_text(errors="replace")


def results(repository, run):
    attempt = run["run_attempt"]
    # Pin the jobs endpoint to the selected attempt so a later retry cannot
    # silently change the evidence after the review has started.
    endpoint = (
        f"repos/{repository}/actions/runs/{run['id']}/attempts/{attempt}"
        "/jobs?per_page=100"
    )
    jobs = [job for page in gh(endpoint) for job in page["jobs"]]
    data = {
        "head_sha": run["head_sha"],
        "run_url": run["html_url"],
        "attempt": attempt,
        "conclusion": run["conclusion"],
        "jobs": [
            {
                "id": job["id"],
                "name": job["name"],
                "html_url": job["html_url"],
                "conclusion": job["conclusion"],
                "steps": job.get("steps", []),
            }
            for job in jobs
        ],
    }
    if run["conclusion"] == "failure":
        data["failed_job_excerpts"] = failed_logs(repository, run["id"], attempt)
    return data


def selected_results(repository, run_id, attempt, head_sha):
    endpoint = f"repos/{repository}/actions/runs/{run_id}/attempts/{attempt}"
    run = gh(endpoint)[0]
    if run["head_sha"] != head_sha:
        raise ValueError("CI run does not match the requested commit")
    if run["run_attempt"] != attempt or classify(run) != "ready":
        raise ValueError("Selected CI attempt is not ready")
    return results(repository, run)
