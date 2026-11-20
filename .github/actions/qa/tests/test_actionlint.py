"""Ensure workflow validation rejects invalid GitHub Actions expressions."""

import subprocess


def test_actionlint_rejects_unknown_github_context_property():
    workflow = """name: Test
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: echo ok
        env:
          VALUE: ${{ github.property_that_does_not_exist }}
"""
    result = subprocess.run(
        ["actionlint", "-"], input=workflow, capture_output=True, text=True
    )
    assert result.returncode != 0
    assert 'property "property_that_does_not_exist" is not defined' in result.stdout
