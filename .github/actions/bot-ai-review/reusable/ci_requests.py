"""Read bot-authored request records used by the CI review coordinator."""

import hashlib
import hmac
import json
import os
import re
import subprocess
from urllib.parse import urlencode

from ci_results import AmbiguousCIError, classify, gh, select_run

# Do not pass the signing key to gh or other child processes.
STATE_KEY = os.environ.pop("CI_STATE_KEY", "").encode()
MARKER = re.compile(r"<!-- ai-review-request (\{.*\}) ([0-9a-f]{64}) -->")


def record_body(request, message):
    if not STATE_KEY:
        raise ValueError("CI request signing key is unavailable")
    payload = json.dumps(request, separators=(",", ":"), sort_keys=True)
    signature = hmac.new(STATE_KEY, payload.encode(), hashlib.sha256).hexdigest()
    return f"{message}\n\n<!-- ai-review-request {payload} {signature} -->"


def parse_record(comment, app_id):
    """Trust only a signed record bound to this app comment.

    Other bots use the same app and may quote untrusted text.
    """
    app = comment.get("performed_via_github_app") or {}
    if app.get("id") != app_id:
        return None
    match = MARKER.search(comment.get("body") or "")
    if not match or not STATE_KEY:
        return None
    expected = hmac.new(STATE_KEY, match.group(1).encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, match.group(2)):
        return None
    try:
        record = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    if not isinstance(record, dict) or record.get("record_id") != comment.get("id"):
        return None
    return record


def active_request(comments, app_id, stage, head_sha):
    for comment in comments:
        record = parse_record(comment, app_id)
        if record and (
            record.get("stage") == stage
            and record.get("head_sha") == head_sha
            and record.get("state") in ("waiting", "reviewing")
        ):
            return comment
    return None


def resume_record(api, dispatch, app_id, repository, pr_number):
    """Resume only an app-authored dispatch for a signed waiting record on this PR."""
    app = dispatch.get("performed_via_github_app") or {}
    match = re.fullmatch(r"/ai-review-resume ([0-9]+)", dispatch.get("body") or "")
    if app.get("id") != app_id or not match:
        return None
    comment = api.comment(int(match.group(1)))
    issue_url = f"https://api.github.com/repos/{repository}/issues/{pr_number}"
    record = parse_record(comment, app_id)
    if (
        comment.get("issue_url") != issue_url
        or not record
        or record.get("state") != "waiting"
        or record.get("repository") != repository
        or record.get("pr_number") != pr_number
    ):
        return None
    return comment


def register(api, app_id, pr_number, request, pr):
    # The caller must serialize registration and resumption so both cannot
    # claim the same request between reading and updating its comment.
    comments = api.comments(pr_number)
    existing = active_request(comments, app_id, request["stage"], request["head_sha"])
    if existing:
        old = parse_record(existing, app_id)
        review_run_id = old.get("review_run_id")
        if old.get("base_ref") != request.get("base_ref"):
            old["state"] = "done"
            api.update(
                existing["id"],
                record_body(old, "The pull request changed base; review skipped."),
            )
        elif old["state"] == "waiting":
            # A failed update or a lost completion event can leave CI finished
            # while the request still says waiting. Recheck the same record.
            old["review_run_id"] = request.get("review_run_id")
            request.clear()
            request.update(old)
            return check_ci(api, existing["id"], request, pr)
        else:
            if not review_run_id:
                return "duplicate", None, None
            # A workflow can fail before its cleanup job. Recover on the next
            # request only after GitHub confirms that workflow is no longer running.
            if api.workflow_run(review_run_id)["status"] != "completed":
                return "duplicate", None, None
            old["state"] = "done"
            api.update(
                existing["id"],
                record_body(old, "Previous review ended without cleanup."),
            )
    request = {**request, "state": "waiting"}
    # Bind the signed request to its actual comment ID before checking CI.
    # A completion during registration is caught by the subsequent CI check.
    comment_id = api.create(pr_number, "Checking primary CI.")
    request["record_id"] = comment_id
    api.update(comment_id, record_body(request, "Checking primary CI."))
    return check_ci(api, comment_id, request, pr)


def resume(api, comment, app_id, pr, review_run_id=None):
    request = parse_record(comment, app_id)
    if not request or request.get("state") != "waiting":
        return "ignored", None, None
    request["review_run_id"] = review_run_id
    if not is_current(pr, request):
        request["state"] = "done"
        api.update(
            comment["id"],
            record_body(request, "The pull request changed or closed; review skipped."),
        )
        return "stopped", comment["id"], None
    return check_ci(api, comment["id"], request, pr)


def coordinate(
    api, app_id, repository, pr_number, request, dispatch, review_run_id=None
):
    if dispatch is not None:
        comment = resume_record(api, dispatch, app_id, repository, pr_number)
        if comment is None:
            return {}
        request = parse_record(comment, app_id)
    else:
        request = {**request, "repository": repository, "pr_number": pr_number}
    request["review_run_id"] = review_run_id
    pr = api.pull(pr_number)
    if dispatch is None:
        if not is_current(pr, request):
            api.create(pr_number, "The pull request changed or closed; review skipped.")
            return {}
        state, record_id, run = register(api, app_id, pr_number, request, pr)
    else:
        state, record_id, run = resume(api, comment, app_id, pr, review_run_id)
    if state != "ready":
        return {}
    return {
        **request,
        "record_id": record_id,
        "run_id": run["id"],
        "attempt": run["run_attempt"],
    }


def wake(api, app_id, run):
    if (
        run.get("path") != ".github/workflows/ci.yml"
        or run.get("event") != "pull_request"
    ):
        return
    for pr in api.pulls_for_run(run):
        for comment in api.comments(pr["number"]):
            request = parse_record(comment, app_id)
            if (
                request
                and request.get("state") == "waiting"
                and request.get("head_sha") == run["head_sha"]
                and request.get("pr_number") == pr["number"]
            ):
                api.create(pr["number"], f"/ai-review-resume {comment['id']}")


def finish(api, app_id, pr_number, comment_id, publication_result):
    comment = api.comment(comment_id)
    request = parse_record(comment, app_id)
    if not request or request.get("state") != "reviewing":
        return
    pr = api.pull(pr_number)
    request["state"] = "done"
    if not is_current(pr, request):
        message = "The pull request changed or closed; review skipped."
    elif publication_result == "success":
        message = "CI-aware review completed."
    else:
        message = "CI-aware review did not complete. Request another review."
    api.update(comment_id, record_body(request, message))


def is_current(pr, request):
    """Reject a retargeted PR even when its head commit has not changed."""
    return (
        pr["state"] == "open"
        and pr["head"]["sha"] == request["head_sha"]
        and pr.get("base", {}).get("ref") == request.get("base_ref")
    )


def check_ci(api, comment_id, request, pr):
    try:
        if request.get("run_id") and request.get("attempt"):
            # A retry started after the selected attempt finished must not
            # postpone the review when its completion event arrives late.
            run = api.run_attempt(request["run_id"], request["attempt"])
        else:
            run = api.ci_run(pr)
    except AmbiguousCIError as error:
        request["state"] = "done"
        api.update(
            comment_id,
            record_body(
                request,
                f"{error}. Request a new review when CI matches this pull request.",
            ),
        )
        raise
    except Exception:
        request["state"] = "done"
        api.update(
            comment_id,
            record_body(request, "Could not check CI. Request a new review."),
        )
        raise
    if run is None:
        request["state"] = "done"
        api.update(
            comment_id,
            record_body(request, "No matching CI run. Request a new review."),
        )
        return "stopped", comment_id, None
    state = classify(run)
    request["state"] = {"ready": "reviewing", "waiting": "waiting", "stopped": "done"}[
        state
    ]
    request["run_id"] = run["id"]
    request["attempt"] = run["run_attempt"]
    if state == "waiting":
        message = f"Waiting for CI for {request['head_sha']}: {run['html_url']}"
    elif state == "ready":
        message = f"Reviewing {request['head_sha']} with CI results: {run['html_url']}"
    else:
        message = f"CI did not finish successfully or fail: {run['html_url']}. Request a new review."
    api.update(comment_id, record_body(request, message))
    return state, comment_id, run


class GitHub:
    def __init__(self, repository):
        self.repository = repository

    def comments(self, pr_number):
        endpoint = f"repos/{self.repository}/issues/{pr_number}/comments?per_page=100"
        return [comment for page in gh(endpoint) for comment in page]

    def comment(self, comment_id):
        return gh(f"repos/{self.repository}/issues/comments/{comment_id}")[0]

    def pull(self, pr_number):
        return gh(f"repos/{self.repository}/pulls/{pr_number}")[0]

    def workflow_run(self, run_id):
        return gh(f"repos/{self.repository}/actions/runs/{run_id}")[0]

    def run_attempt(self, run_id, attempt):
        endpoint = f"repos/{self.repository}/actions/runs/{run_id}/attempts/{attempt}"
        return gh(endpoint)[0]

    def pulls_for_run(self, run):
        """Find candidate PRs by source branch, including forks GitHub omits from the run."""
        numbers = {item["number"] for item in run.get("pull_requests", [])}
        source = run.get("head_repository") or {}
        full_name = source.get("full_name", "")
        if "/" in full_name and run.get("head_branch"):
            owner = full_name.split("/", 1)[0]
            query = urlencode(
                {
                    "state": "all",
                    "head": f"{owner}:{run['head_branch']}",
                    "per_page": 100,
                }
            )
            pages = gh(f"repos/{self.repository}/pulls?{query}")
            for page in pages:
                for pr in page:
                    repo = pr["head"].get("repo") or {}
                    if repo.get("full_name", "").lower() == full_name.lower():
                        numbers.add(pr["number"])
        return [{"number": number} for number in sorted(numbers)]

    def create(self, pr_number, body):
        endpoint = f"repos/{self.repository}/issues/{pr_number}/comments"
        return self.write("POST", endpoint, body)["id"]

    def update(self, comment_id, body):
        endpoint = f"repos/{self.repository}/issues/comments/{comment_id}"
        self.write("PATCH", endpoint, body)

    def write(self, method, endpoint, body):
        output = subprocess.check_output(
            ["gh", "api", "--method", method, endpoint, "--input", "-"],
            input=json.dumps({"body": body}),
            text=True,
        )
        return json.loads(output)

    def ci_run(self, pr):
        """Find the latest primary run only when its source branch identifies one PR."""
        sha = pr["head"]["sha"]
        endpoint = (
            f"repos/{self.repository}/actions/workflows/ci.yml/runs"
            f"?event=pull_request&head_sha={sha}&per_page=100"
        )
        runs = [run for page in gh(endpoint) for run in page["workflow_runs"]]
        run = select_run(runs, pr)
        if run:
            candidates = self.pulls_for_run(run)
            if len(candidates) != 1 or candidates[0]["number"] != pr["number"]:
                raise AmbiguousCIError(
                    "CI run cannot be uniquely matched to multiple pull requests"
                )
            # A run for the same head can predate a retarget and test the old
            # base. GitHub's current PR association does not establish its base.
            endpoint = (
                f"repos/{self.repository}/issues/{pr['number']}/events?per_page=100"
            )
            events = [event for page in gh(endpoint) for event in page]
            if any(
                event.get("event")
                in ("base_ref_changed", "automatic_base_change_succeeded")
                and event["created_at"] >= run["created_at"]
                for event in events
            ):
                raise AmbiguousCIError("CI run predates a base branch change")
        return run
