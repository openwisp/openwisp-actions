Changelog
=========

Version 0.2.0 [2026-11-18]
--------------------------

Features
~~~~~~~~

- Added reusable on-demand AI review workflow `#15
  <https://github.com/openwisp/openwisp-actions/issues/15>`_

  Added a reusable GitHub Actions workflow for on-demand AI code reviews
  supporting `/review`, `/security-review`, and `/final-review` commands.
  This provides automated checks for pull request direction, threat
  models, security vulnerabilities, and review history status.

Changes
~~~~~~~

Other changes
+++++++++++++

- Enabled reusable workflows

  Enabled the CI failure, issue assignment, stale PR, and backport
  workflows for this repository. Used the retry action in CI and added a
  changelog runner that verifies approvals and fetches PR data safely.

Dependencies
++++++++++++

- Bumped ``openwisp-utils~=1.3.1``

  Updates the requirements on `openwisp-utils
  <https://github.com/openwisp/openwisp-utils>`__ to permit the latest
  version. - `Release notes
  <https://github.com/openwisp/openwisp-utils/releases>`__ - `Changelog
  <https://github.com/openwisp/openwisp-utils/blob/master/CHANGES.rst>`__
  - `Commits
  <https://github.com/openwisp/openwisp-utils/compare/1.3.0...1.3.1>`__

- Update google-genai requirement

  Updates the requirements on `google-genai
  <https://github.com/googleapis/python-genai>`__ to permit the latest
  version. - `Release notes
  <https://github.com/googleapis/python-genai/releases>`__ - `Changelog
  <https://github.com/googleapis/python-genai/blob/main/CHANGELOG.md>`__ -
  `Commits
  <https://github.com/googleapis/python-genai/compare/v2.31.0...v2.33.0>`__

Bugfixes
~~~~~~~~

- Fixed bot dependencies and cached Python packages
- Replaced fork checkout in CI failure bot `#794
  <https://github.com/openwisp/openwisp-actions/issues/794>`_

  Fetched the failed PR diff from the GitHub API instead of checking out
  untrusted code. Filtered source context and retained the size limit and
  fallback behavior when the diff is unavailable.

  Passed the failed run's base SHA when available and used the bot token
  for the PR metadata fallback. Added regression tests and updated the
  workflow documentation.

Version 0.1.1 [2026-10-27]
--------------------------

Bugfixes
~~~~~~~~

- Fixed an issue where successive pushes could cause pending version
  branch replication jobs to be cancelled, resulting in missed updates.
- Fixed backport failures when changes included files in
  ``.github/workflows/``.

Version 0.1.0 [2026-10-26]
--------------------------

Features
~~~~~~~~

- Migrated reusable GitHub Actions and workflows from ``openwisp-utils``
  to ``openwisp-actions``, providing a dedicated repository for
  maintaining and sharing GitHub Actions automation across OpenWISP
  projects.
