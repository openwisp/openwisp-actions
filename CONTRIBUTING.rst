Please refer to the `OpenWISP Contribution Guidelines
<https://openwisp.io/docs/dev/developer/contributing.html>`_.

For the local environment and validation commands, see the `Development
section <README.rst#development>`_ of the README.

Workflow and Action Scripts
===========================

Keep workflows and composite actions focused on orchestration. Keep the
entry point and named helper scripts directly in
``.github/actions/<name>/scripts/``. Place tests in ``tests/`` and test
the scripts directly rather than extracting commands from YAML.

Use ``scripts/__main__.py`` for a Python entry point. Python recognizes
``__main__.py`` when a directory is executed as a module or script. Use
``scripts/__main__.sh`` as the repository's shell entry-point convention.
Dispatch separate workflow steps with subcommands, keeping their outputs,
permissions, and failure handling separate.

Reusable workflows must check out their implementation from
``job.workflow_repository`` at ``job.workflow_sha``. When scripts operate
on the caller's repository, keep that checkout separate from the scripts
checkout. Composite actions locate scripts with ``github.action_path``.

The QA checks validate JSON and GraphQL syntax as well as Python, shell,
YAML, and GitHub Actions workflows. Run ``./run-qa-checks`` and
``./runtests`` after behavior changes.
