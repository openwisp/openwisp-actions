"""Test review command and model selection."""

import os
import subprocess
import tempfile
import unittest

SCRIPTS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reusable"
)
SCRIPT = os.path.join(SCRIPTS, "parse_command.sh")
VARIABLES = {
    "PROVIDER": "provider",
    "GENERAL_MODEL": "general",
    "SECURITY_MODEL": "security",
    "FINAL_MODEL": "final",
}


def parse(body, **overrides):
    with tempfile.NamedTemporaryFile("r", encoding="utf-8") as output:
        env = {"PATH": os.environ["PATH"], "BODY": body, "GITHUB_OUTPUT": output.name}
        env.update({k: v for k, v in {**VARIABLES, **overrides}.items() if v})
        subprocess.run(["bash", SCRIPT], env=env, check=True, capture_output=True)
        return dict(line.split("=", 1) for line in output.read().splitlines())


class TestParseCommand(unittest.TestCase):
    def test_selects_stage_and_model_variable(self):
        cases = [
            ("/review", "review", "provider/general"),
            ("  /review \r\n", "review", "provider/general"),
            ("/security-review", "security-review", "provider/security"),
            ("/final-review", "final-review", "provider/final"),
        ]
        for body, stage, model in cases:
            with self.subTest(body=body):
                self.assertEqual(parse(body), {"stage": stage, "model": model})

    def test_leaves_model_empty_when_a_variable_is_unset(self):
        cases = [
            ("/review", {"PROVIDER": ""}),
            ("/review", {"GENERAL_MODEL": ""}),
            ("/security-review", {"SECURITY_MODEL": ""}),
            ("/final-review", {"FINAL_MODEL": ""}),
        ]
        for body, overrides in cases:
            with self.subTest(body=body, overrides=overrides):
                self.assertEqual(parse(body, **overrides), {"stage": body[1:]})

    def test_ignores_other_comments(self):
        cases = [
            "please /review",
            "/reviewx",
            "/review gpt",
            "/review copilot/gpt-6.1-terra",
            "/security-review opencode/deepseek-v4.1-flash-free",
            "/review; rm -rf /",
        ]
        for body in cases:
            with self.subTest(body=body):
                self.assertEqual(parse(body), {})

    def test_selects_the_effort_for_each_stage(self):
        efforts = {
            "GENERAL_EFFORT": "high",
            "SECURITY_EFFORT": "xhigh",
            "FINAL_EFFORT": "max",
        }
        for command, effort in (
            ("/review", "high"),
            ("/security-review", "xhigh"),
            ("/final-review", "max"),
        ):
            with self.subTest(command=command):
                self.assertEqual(parse(command, **efforts)["effort"], effort)

    def test_rejects_effort_with_newline(self):
        with self.assertRaises(subprocess.CalledProcessError):
            parse("/review", GENERAL_EFFORT="high\nmodel=other/model")


if __name__ == "__main__":
    unittest.main()
