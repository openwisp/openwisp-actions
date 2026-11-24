"""Test review inputs and incomplete model runs."""

import json
import os
import subprocess
import tempfile
import unittest

SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "reusable",
    "run_review.sh",
)


class TestRunReview(unittest.TestCase):
    def test_failed_run_cannot_publish_partial_approval(self):
        event = {
            "type": "text",
            "part": {
                "text": json.dumps(
                    {
                        "verdict": "Ready to merge",
                        "title": "OK",
                        "summary": "Fine",
                        "comments": [],
                    }
                )
            },
        }
        root, result = self.run_review(event, status=1)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(os.path.exists(os.path.join(root, "findings.json")))
        with open(os.path.join(root, "events.jsonl")) as f:
            self.assertEqual(json.load(f), event)
        self.assertIn(b"The model run did not complete (exit status: 1)", result.stdout)

    def test_final_review_receives_base_branch_guidance(self):
        event = {"type": "text", "part": {"text": "not JSON"}}
        root, result = self.run_review(event, guidance=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        with open(os.path.join(root, "args")) as f:
            args = f.read().splitlines()
        self.assertIn(f"{root}/data/guidance.md", args)

    def test_passes_valid_effort_and_omits_unset_effort(self):
        event = {"type": "text", "part": {"text": "not JSON"}}
        for effort in ("", "xhigh"):
            with self.subTest(effort=effort):
                root, result = self.run_review(event, effort=effort)
                self.assertEqual(result.returncode, 0, result.stderr)
                with open(os.path.join(root, "args")) as f:
                    args = f.read().splitlines()
                if effort:
                    index = args.index("--variant")
                    self.assertEqual(args[index + 1], effort)
                else:
                    self.assertNotIn("--variant", args)

    def test_rejects_unsupported_effort_before_running_review(self):
        event = {"type": "text", "part": {"text": "not JSON"}}
        root, result = self.run_review(event, effort="max")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(os.path.exists(os.path.join(root, "args")))
        self.assertFalse(os.path.exists(os.path.join(root, "findings.json")))

    def test_rejects_missing_or_invalid_model_metadata(self):
        event = {"type": "text", "part": {"text": "not JSON"}}
        for metadata in ('other/model\n{"variants":{"xhigh":{}}}', "provider/model\n{"):
            with self.subTest(metadata=metadata):
                root, result = self.run_review(event, effort="xhigh", metadata=metadata)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(os.path.exists(os.path.join(root, "args")))

    def test_finds_variants_for_selected_model_in_provider_catalog(self):
        event = {"type": "text", "part": {"text": "not JSON"}}
        metadata = (
            'provider/other\n{"variants": {"high": {}}}\n'
            'provider/model\n{\n  "variants": {"xhigh": {}}\n}\n'
            'provider/last\n{"variants": {}}\n'
        )
        root, result = self.run_review(event, effort="xhigh", metadata=metadata)
        self.assertEqual(result.returncode, 0, result.stderr)
        with open(os.path.join(root, "args")) as f:
            self.assertIn("--variant\nxhigh\n", f.read())

    def run_review(
        self,
        event,
        status=0,
        guidance=False,
        effort="",
        metadata=None,
        ci_results=False,
        auth=None,
        grep_script=None,
        model="provider/model",
    ):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = directory.name
        for name in ("bin", "pr", "data", "shared-guidance"):
            os.mkdir(os.path.join(root, name))
        if auth is not None:
            auth_dir = os.path.join(root, "opencode-data", "opencode")
            os.makedirs(auth_dir)
            with open(os.path.join(auth_dir, "auth.json"), "w") as f:
                if isinstance(auth, str):
                    f.write(auth)
                else:
                    json.dump({model.split("/")[0]: auth}, f)
        files = ["pr.diff", "context.json", "history.json"]
        if guidance:
            files.append("guidance.md")
        if ci_results:
            files.append("ci-results.json")
        for name in files:
            with open(os.path.join(root, "data", name), "w") as f:
                f.write("guidance")
        with open(os.path.join(root, "shared-guidance", "guidance.md"), "w") as f:
            f.write("")
        fake = os.path.join(root, "bin", "opencode")
        with open(fake, "w") as f:
            f.write(
                "#!/bin/sh\n"
                "if [ \"$1\" = debug ]; then echo '[]'; exit 0; fi\n"
                'if [ "$1" = models ]; then\n'
                '  if [ "${3:-}" = --verbose ]; then printf "%s\\n" "$MODEL_METADATA"; fi\n'
                "  exit 0\n"
                "fi\n"
                'printf \'%s\\n\' "$@" >"$RUNNER_TEMP/args"\n'
                "printf '%s\\n' \"$EVENT\"\n"
                'exit "$MODEL_STATUS"\n'
            )
        os.chmod(fake, 0o755)
        if grep_script:
            grep = os.path.join(root, "bin", "grep")
            with open(grep, "w") as f:
                f.write(grep_script)
            os.chmod(grep, 0o755)
        env = {
            **os.environ,
            "PATH": f"{root}/bin:{os.environ['PATH']}",
            "RUNNER_TEMP": root,
            "PR_DIR": f"{root}/pr",
            "DATA_DIR": f"{root}/data",
            "MODEL": model,
            "EFFORT": effort,
            "MODEL_METADATA": metadata or 'provider/model\n{"variants":{"xhigh":{}}}',
            "STAGE": "final-review",
            "EVENT": json.dumps(event),
            "MODEL_STATUS": str(status),
        }
        return root, subprocess.run(["bash", SCRIPT], env=env, capture_output=True)

    def test_ci_results_are_attached_when_available(self):
        event = {"type": "text", "part": {"text": "not JSON"}}
        root, result = self.run_review(event, ci_results=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        with open(os.path.join(root, "args")) as f:
            self.assertIn(f"{root}/data/ci-results.json", f.read().splitlines())

    def test_failed_model_run_logs_error_event(self):
        event = {
            "type": "error",
            "error": {"data": {"message": "Provider unavailable"}},
        }
        root, result = self.run_review(event, status=1)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"Error: Provider unavailable", result.stdout)
        self.assertFalse(os.path.exists(os.path.join(root, "findings.json")))

    def test_failed_model_run_does_not_log_access_token(self):
        event = {"type": "error", "error": {"data": {"message": "access-secret"}}}
        _, result = self.run_review(
            event,
            status=1,
            auth={"refresh": "refresh-secret", "access": "access-secret"},
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"The model output contains a credential", result.stdout)
        self.assertNotIn(b"access-secret", result.stdout)

    def test_malformed_auth_stops_before_logging_model_output(self):
        event = {"type": "error", "error": {"data": {"message": "secret-value"}}}
        root, result = self.run_review(event, status=1, auth='{"access":"secret-value"')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn(b"secret-value", result.stdout)
        self.assertIn(b"Could not check model output for credentials", result.stdout)
        self.assertFalse(os.path.exists(f"{root}/opencode-data/opencode/auth.json"))

    def test_credential_scan_does_not_put_token_in_arguments(self):
        event = {"type": "error", "error": {"data": {"message": "access-secret"}}}
        root, result = self.run_review(
            event,
            status=1,
            auth={"access": "access-secret"},
            grep_script='#!/bin/sh\nprintf "%s\\n" "$@" >"$RUNNER_TEMP/grep-args"\nexec /usr/bin/grep "$@"\n',
        )
        self.assertIn(b"The model output contains a credential", result.stdout)
        with open(os.path.join(root, "grep-args")) as f:
            self.assertNotIn("access-secret", f.read())

    def test_credential_scan_error_stops_before_logging_model_output(self):
        event = {"type": "error", "error": {"data": {"message": "provider message"}}}
        _, result = self.run_review(
            event,
            status=1,
            auth={"access": "access-secret"},
            grep_script="#!/bin/sh\nexit 2\n",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"Could not check model output for credentials", result.stdout)
        self.assertNotIn(b"provider message", result.stdout)

    def test_nonmatching_credentials_allow_failed_run_diagnostics(self):
        event = {
            "type": "error",
            "error": {"data": {"message": "Provider unavailable"}},
        }
        _, result = self.run_review(
            event,
            status=1,
            auth={"refresh": "refresh-secret", "access": "access-secret"},
            model="github-copilot/model",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"Error: Provider unavailable", result.stdout)
        self.assertIn(b"The model run did not complete", result.stdout)

    def test_missing_copilot_credentials_stop_before_logging(self):
        event = {"type": "error", "error": {"data": {"message": "secret-value"}}}
        for auth in (None, "", "   ", "{}", '{"other": {"access": "other-token"}}'):
            with self.subTest(auth=auth):
                _, result = self.run_review(
                    event, status=1, auth=auth, model="github-copilot/model"
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(
                    b"Could not check model output for credentials", result.stdout
                )
                self.assertNotIn(b"secret-value", result.stdout)
