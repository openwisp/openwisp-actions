# AGENTS.md

## Project Overview

`openwisp-actions` maintains reusable GitHub Actions and workflows for OpenWISP repositories.

- Reusable workflows are in `.github/workflows/reusable-*.yml`.
- Composite actions and Python automation scripts are in `.github/actions/`.
- Tests are maintained with the action implementation they cover in `.github/actions/`.
- `README.rst` documents public workflow and action interfaces.

## Source of Truth

- Use `.github/workflows/ci.yml` for CI commands and supported Python versions.
- Use `README.rst` for public action and reusable-workflow interfaces.
- Use `CONTRIBUTING.rst` for local setup and validation commands.
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
- Update `README.rst` and `CONTRIBUTING.rst` when public interfaces, setup steps, validation commands, or supported versions change.

## Testing and QA

- Run targeted pytest collections while iterating. Do not routinely run unrelated test collections.
- Keep test success output quiet. Capture and assert expected stdout or stderr when code under test writes output.
- Run `./run-qa-checks` to check Python formatting, import ordering, linting, and documentation formatting.
- Run `zizmor --offline --persona=auditor .` after GitHub Actions security changes.

## GitHub Actions Security

- Pin third-party actions to full commit SHAs and include their release version in an inline comment.
- Set top-level workflow permissions to `{}` and grant each job only the permissions it needs.
- Do not interpolate GitHub expression values directly into shell commands. Pass them through environment variables.
- Check out reusable workflow scripts with `${{ job.workflow_repository }}` and `${{ job.workflow_sha }}` when executing trusted repository code.
- Do not expose secrets in logs, shell output, workflow outputs, or generated artifacts.
- Treat pull request code and event payloads as untrusted data. Do not execute code from untrusted pull requests in privileged workflows.

## Troubleshooting

If `README.rst` or `CONTRIBUTING.rst` differs from CI, use `.github/workflows/ci.yml` for verification and report the exact discrepancy. Do not change documentation unless the change caused the divergence or the user explicitly requests it.
