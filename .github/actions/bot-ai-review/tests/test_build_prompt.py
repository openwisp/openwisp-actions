import os
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "build-prompt.sh")
PROMPTS = os.path.join(ROOT, "prompts")


def read(name):
    with open(os.path.join(PROMPTS, name)) as f:
        return f.read()


class TestBuildPrompt(unittest.TestCase):
    def build(self, stage, minutes="50"):
        with tempfile.NamedTemporaryFile("w", suffix=".md") as guidance:
            guidance.write("Shared guidance.\n")
            guidance.flush()
            return subprocess.run(
                [SCRIPT, stage, minutes, guidance.name],
                capture_output=True,
                text=True,
                check=True,
            ).stdout

    def test_starts_with_shared_context_and_fills_in_the_limit(self):
        for stage, prompt in (
            ("review", "stages/1-review.md"),
            ("security-review", "stages/2-security-review.md"),
            ("final-review", "stages/3-final-review.md"),
        ):
            with self.subTest(stage=stage):
                output = self.build(stage)
                shared = read("shared/context.md").replace("{{REVIEW_MINUTES}}", "50")
                self.assertTrue(output.startswith(shared))
                self.assertIn("stopped after 50 minutes", output)
                self.assertNotIn("{{", output)
                parts = [
                    read(prompt),
                    "Shared guidance.\n",
                    read("shared/verification.md"),
                ]
                self.assertTrue(output.endswith("".join(parts)))

    def test_uses_the_given_limit(self):
        self.assertIn("stopped after 25 minutes", self.build("review", "25"))


if __name__ == "__main__":
    unittest.main()
