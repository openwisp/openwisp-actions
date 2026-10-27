Changelog
=========

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
