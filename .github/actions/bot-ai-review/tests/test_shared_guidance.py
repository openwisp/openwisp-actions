"""Test extraction of shared OpenWISP review guidance."""

import os
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reusable"
)
sys.path.insert(0, SCRIPTS)

from shared_guidance import INTRO, SECTIONS, build, extract  # noqa: E402

SCRIPT = os.path.join(SCRIPTS, "shared_guidance.py")
AGENTS = """# Global Rules

## Rule-Following Verification

Not copied.

## Writing Style

Intro.

### Plain Language

Use everyday words.

### Punctuation and Characters

No em dashes.

## Repository Instructions

Read AGENTS.md.

## Scope And Autonomy

Not copied.

## Credential Safety

Never expose credentials.

## Reviews

Report only verified findings.
"""


class TestExtract(unittest.TestCase):
    def test_includes_subsections_until_the_next_section(self):
        self.assertEqual(
            extract(AGENTS, "Writing Style"),
            "## Writing Style\n\nIntro.\n\n### Plain Language\n\n"
            "Use everyday words.\n\n### Punctuation and Characters\n\n"
            "No em dashes.",
        )

    def test_reads_the_last_section(self):
        self.assertEqual(
            extract(AGENTS, "Reviews"), "## Reviews\n\nReport only verified findings."
        )

    def test_returns_none_for_missing_or_renamed_heading(self):
        for title in ("Testing", "Review", "Plain Language"):
            with self.subTest(title=title):
                self.assertIsNone(extract(AGENTS, title))


class TestBuild(unittest.TestCase):
    def test_copies_only_the_selected_sections(self):
        guidance, notes = build(AGENTS)
        self.assertEqual(notes, [])
        self.assertTrue(guidance.startswith(INTRO))
        for title in SECTIONS:
            self.assertIn(f"## {title}\n", guidance)
        self.assertNotIn("Not copied.", guidance)

    def test_notes_missing_sections_and_keeps_the_others(self):
        text = AGENTS.replace("## Reviews", "## Code Reviews")
        guidance, notes = build(text)
        self.assertEqual(
            notes, ['- Note: shared AI guidance section "Reviews" was not found.']
        )
        self.assertIn("## Credential Safety", guidance)
        self.assertNotIn("Report only verified findings.", guidance)

    def test_notes_a_failed_download(self):
        self.assertEqual(
            build(None),
            ("", ["- Note: the shared AI guidance could not be downloaded."]),
        )

    def test_has_no_guidance_when_every_section_is_missing(self):
        guidance, notes = build("# Rules\n")
        self.assertEqual(guidance, "")
        self.assertEqual(len(notes), len(SECTIONS))


class TestMain(unittest.TestCase):
    def run_script(self, source):
        with tempfile.TemporaryDirectory() as directory:
            guidance = os.path.join(directory, "guidance.md")
            notes = os.path.join(directory, "notes.md")
            subprocess.run(
                [sys.executable, SCRIPT, source, guidance, notes],
                check=True,
                capture_output=True,
            )
            with open(guidance) as g, open(notes) as n:
                return g.read(), n.read()

    def test_writes_guidance_and_notes(self):
        with tempfile.NamedTemporaryFile("w", suffix=".md") as source:
            source.write(AGENTS.replace("## Credential Safety", "## Secrets"))
            source.flush()
            guidance, notes = self.run_script(source.name)
        self.assertIn("## Reviews", guidance)
        self.assertEqual(
            notes,
            '- Note: shared AI guidance section "Credential Safety" was not found.\n',
        )

    def test_handles_a_missing_download(self):
        guidance, notes = self.run_script("/nonexistent/AGENTS.md")
        self.assertEqual(guidance, "")
        self.assertEqual(
            notes, "- Note: the shared AI guidance could not be downloaded.\n"
        )


if __name__ == "__main__":
    unittest.main()
