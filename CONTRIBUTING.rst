Contributing to OpenWISP Actions
================================

For the shared contribution process, see the `OpenWISP Contribution
Guidelines <https://openwisp.io/docs/dev/developer/contributing.html>`_.

Local Development
-----------------

Run these commands from the repository root on Linux with Python 3.13, the
version used in `CI <.github/workflows/ci.yml>`_. The tests also use Bash,
Git, jq, rsync, flock, and OpenSSL.

.. code-block:: shell

    python3.13 -m venv .venv
    source .venv/bin/activate
    python -m pip install -r requirements-test.txt
    ./run-qa-checks
    ./runtests

While changing one action, run just its tests. For example:

.. code-block:: shell

    python -m pytest .github/actions/backport/tests -q

Use ``openwisp-qa-format`` to format supported files. ``./run-qa-checks``
checks Python, shell, YAML, and reStructuredText, parses JSON and GraphQL,
and runs actionlint and zizmor. The shell and YAML line limit is 110
characters, and inline workflow and composite-action ``run:`` blocks can
contain up to five lines.

The `QA script <run-qa-checks>`_ lists the specific diagnostics it ignores
for GitHub Actions features that actionlint 1.7.12 does not recognize.

Workflow and Action Scripts
---------------------------

See `Workflow Architecture and Script Structure
<AGENTS.md#workflow-architecture-and-script-structure>`_ for where to put
scripts and tests, and which logic belongs in YAML.

Use ``scripts/__main__.py`` for a Python entry point. Python recognizes
``__main__.py`` when a directory is executed as a module or script. Use
``scripts/__main__.sh`` as the repository's shell entry-point convention.

Keep the caller checkout separate from trusted workflow scripts whenever a
script works on the caller's repository. For example, the backport
workflow starts ``__main__.sh`` from the trusted checkout but runs Git in
the caller checkout. Composite actions locate their scripts with
``github.action_path``.
