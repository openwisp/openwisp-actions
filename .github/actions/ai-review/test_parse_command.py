import os
import subprocess
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "parse-command.sh")
TERRA = "github-copilot/gpt-6.1-terra"
ASTRA = "github-copilot/gpt-6-astra"


def parse(body):
    with tempfile.NamedTemporaryFile("r", encoding="utf-8") as output:
        env = {"PATH": os.environ["PATH"], "BODY": body, "GITHUB_OUTPUT": output.name}
        subprocess.run([SCRIPT], env=env, check=True, capture_output=True)
        return dict(line.split("=", 1) for line in output.read().splitlines())


class TestParseCommand(unittest.TestCase):
    def test_selects_stage_and_default_model(self):
        cases = [
            ("/review", "review", TERRA),
            ("  /review \r\n", "review", TERRA),
            ("/security-review", "security-review", ASTRA),
            ("/final-review", "final-review", TERRA),
        ]
        for body, stage, model in cases:
            with self.subTest(body=body):
                self.assertEqual(parse(body), {"stage": stage, "model": model})

    def test_selects_model_from_command(self):
        cases = [
            ("/review copilot/gpt-6.1-terra", "github-copilot/gpt-6.1-terra"),
            (
                "/final-review  opencode/glm-5.3-flash-free",
                "opencode/glm-5.3-flash-free",
            ),
        ]
        for body, model in cases:
            with self.subTest(body=body):
                self.assertEqual(parse(body)["model"], model)

    def test_ignores_other_comments(self):
        cases = [
            "please /review",
            "/reviewx",
            "/review gpt",
            "/review openai/gpt-6",
            "/review copilot/GPT",
            "/review copilot/",
            "/review copilot/x; rm -rf /",
        ]
        for body in cases:
            with self.subTest(body=body):
                self.assertEqual(parse(body), {})


if __name__ == "__main__":
    unittest.main()
