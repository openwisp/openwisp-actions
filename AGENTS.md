# AGENTS.md

## Project Overview

`openwisp-actions` maintains reusable GitHub Actions and workflows for OpenWISP repositories.

- Reusable workflows are in `.github/workflows/reusable-*.yml`.
- Composite actions and Python automation scripts are in `.github/actions/`.
- Tests are maintained with the action implementation they cover in `.github/actions/`.
- `README.rst` documents public workflow and action interfaces.
- Repository-wide QA tools live in `qa/`.

## Source of Truth

- Use `.github/workflows/ci.yml` for CI commands and supported Python versions.
- Use `README.rst` for public interfaces, local setup, and validation commands.
- Keep `CONTRIBUTING.rst` as a link to the general OpenWISP Contribution Guidelines.
- Use the GitHub issue and pull request templates when creating GitHub content.

If instructions conflict, CI configuration wins first, then repository documentation, and this file is supplemental.

## Contributing Guidelines

- Before editing, inspect the affected action or workflow, its tests, documentation, and configuration. Follow existing patterns and do not invent behavior or requirements.
- Keep each contribution focused. Do not include unrelated refactors, formatting churn, or generated files unless explicitly required.
- Add or update focused tests for behavior changes. Use test-driven development for clear bug fixes and narrowly scoped changes.
- Run `./run-qa-checks` and the affected focused tests after changes. Run `./runtests` before marking a behavior-affecting contribution complete.
- When requirements, intended behavior, or an unexpected failure are unclear, stop and seek clarification instead of making speculative changes.
- Create issue branches from `master` using `issues/<issue-number>-<short-title>`.
- Use descriptive, past-tense commit messages. Issue commits must use an allowed OpenWISP prefix and end with `#<issue-number>`.
- Send new commits in response to review feedback instead of amending existing commits.

## Development Rules

- Follow the DRY principle. Do not duplicate workflow logic or Python code across actions.
- Preserve public reusable-workflow inputs, secrets, outputs, default values, and documented behavior unless explicitly required.
- Keep imports at the top of Python files unless a deferred import is necessary.
- Prefer short, precise names that rely on their nearest meaningful scope.
- Add comments only when they explain a non-obvious reason, security constraint, compatibility requirement, or side effect.
- Update `README.rst` when public interfaces, setup steps, validation commands, or supported versions change.

## Testing and QA

- Run targeted pytest collections while iterating. Do not routinely run unrelated test collections.
- Keep test success output quiet. Capture and assert expected stdout or stderr when code under test writes output.
- Run `./run-qa-checks` to check Python formatting, import ordering, linting, and documentation formatting.
- Run `zizmor --offline --persona=auditor .` after GitHub Actions security changes.
- Prefer established QA tools. Add basic tests for custom QA logic that cannot be replaced by those tools.

## GitHub Actions Security

- Pin third-party actions to full commit SHAs and include their release version in an inline comment.
- Set top-level workflow permissions to `{}` and grant each job only the permissions it needs.
- Do not interpolate GitHub expression values directly into shell commands. Pass them through environment variables.
- Check out reusable workflow scripts with `${{ job.workflow_repository }}` and `${{ job.workflow_sha }}` when executing trusted repository code.
- Do not expose secrets in logs, shell output, workflow outputs, or generated artifacts.
- Treat pull request code and event payloads as untrusted data. Do not execute code from untrusted pull requests in privileged workflows.

## Workflow Architecture and Script Structure

Use file and directory names that show readers where to start, what each script does,
and where to find its tests.

- Keep triggers, permissions, and step conditions in YAML. Move non-trivial logic into
  scripts, and use a subcommand when a workflow step needs to call one operation on its own.
- Use one entry point, `__main__.py` or `__main__.sh`, with named helpers beside it in a
  flat `scripts/` directory. For example, the backport workflow calls `__main__.sh parse`
  to read a request and `__main__.sh backport` to apply it. The names point directly to
  `parse.sh` and `backport.sh`.
- Keep simple implementations in the entry point. For example, `retry-command` has
  one retry loop and does not need a separate helper or dispatcher.
- Put tests in `.github/actions/<name>/tests/`, next to `scripts/`. For example,
  `.github/actions/backport/tests/test_backport.py` runs the entry point directly.
  Use YAML tests for workflow wiring that script tests cannot cover.
- Limit inline `run:` blocks to five lines. Enforce this limit with a YAML-aware check.
- Run yamllint with a maximum line length of 110 characters, actionlint, and appropriate linters for every maintained script language in CI.
- Preserve permissions and trust boundaries. Execute reusable-workflow scripts from the workflow repository at `job.workflow_sha` and pass GitHub expressions through environment variables.

## Troubleshooting

If `README.rst` differs from CI, use `.github/workflows/ci.yml` for verification and report the exact discrepancy. Do not change documentation unless the change caused the divergence or the user explicitly requests it.
