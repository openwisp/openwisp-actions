OpenWISP Actions
================

.. image:: https://github.com/openwisp/openwisp-actions/actions/workflows/ci.yml/badge.svg
    :target: https://github.com/openwisp/openwisp-actions/actions/workflows/ci.yml
    :alt: CI build status

.. image:: https://img.shields.io/gitter/room/nwjs/nw.js.svg
    :target: https://gitter.im/openwisp/general
    :alt: chat

----

**OpenWISP Actions** provides reusable GitHub Actions and workflows for
`OpenWISP <https://openwisp.org/>`_. It centralizes common CI and
repository automation so OpenWISP projects can share reviewed behavior and
security controls.

Features
--------

- Retry shell commands that fail transiently in CI.
- Automate issue assignment, pull request validation, stale pull request
  management, and reopen recovery.
- Generate changelog suggestions for approved pull requests.
- Analyze failed CI runs and retry transient failures.
- Backport fixes to stable branches and synchronize derived version
  branches.

----

.. contents:: **Table of Contents**:
    :backlinks: none
    :depth: 3

----

GitHub Actions
--------------

Retry Command
~~~~~~~~~~~~~

This GitHub Action retries a shell command if it fails. It is useful for
handling flaky tests in CI/CD pipelines.

Inputs
++++++

- ``command`` (required): The shell command to run.
- ``max_attempts`` (optional): The number of retry attempts. Defaults to
  ``3``.
- ``delay_seconds`` (optional): The delay between retries in seconds.
  Defaults to ``5``.

Usage Example
+++++++++++++

.. note::

    If the command continues to fail after the specified number of
    attempts, the action will exit with a non-zero status, causing the
    workflow to fail.

See the `CI workflow <.github/workflows/ci.yml>`_ for an example of this
action installing dependencies. In another repository, reference the
`retry-command action <.github/actions/retry-command/action.yml>`_ by its
full repository path and a pinned revision.

Auto-Assignment Bot
~~~~~~~~~~~~~~~~~~~

A collection of Python scripts that automate issue and PR management for
OpenWISP repositories. The bot provides the following features:

- **Issue auto-assignment**: When a contributor opens a valid PR
  referencing an issue (e.g., ``Fixes #123``), the issue is automatically
  assigned to the PR author.
- **Assignment request responses**: When someone comments asking to be
  assigned, the bot checks whether the issue is validated. Contributors
  can start validated issues without assignment when nobody is assigned to
  them. For unvalidated issues, external contributors receive a link to
  the relevant contributing-guidelines section and the developer chat.
  Owners, organization members, and repository collaborators are exempt
  from this validation requirement.
- **Stale PR management**: Warns PR authors after 7 days of inactivity,
  marks stale and unassigns after 14 days, and posts a final follow-up
  encouragement after 60 days. The bot does not auto-close stale PRs.
- **PR reopen reassignment**: When a valid stale PR is reopened, linked
  issues are reassigned back to the author.
- **PR validation**: Enforces the `OpenWISP Contributing Guidelines
  <https://openwisp.io/docs/dev/developer/contributing.html>`_ for
  external contributors. A `validated issue
  <https://openwisp.io/docs/dev/developer/contributing.html#look-for-open-issues>`_
  is required. The bot flags PRs that do not link one. PRs created by the
  configured GitHub App are exempt. The bot removes the ``invalid`` label
  once the PR is valid and closes unresolved invalid PRs 24 hours after
  its warning comment. For valid PRs, it applies the ``ai-review`` label,
  which triggers a CodeRabbit review. The label prevents repeated reviews.
  ``Dependabot`` PRs and PRs whose titles begin with ``[release]`` or
  ``[backport]`` do not receive the label.

How Stale PR Detection Works
++++++++++++++++++++++++++++

The Stale PR job runs daily. For each open PR:

1. **Trigger condition.** The PR is processed only when at least one human
   reviewer's latest non-COMMENTED review is ``CHANGES_REQUESTED``. Bot
   reviews and reviews later superseded by ``APPROVED`` or ``DISMISSED``
   from the same reviewer do not block.
2. **Inactivity** is the time since the more recent of: the PR author's
   latest commit, issue comment, review comment, or review after the
   blocking review; or the blocking review's timestamp if the author has
   not acted since. For commits the date is taken from whichever identity
   (author or committer) matches the PR author, so a maintainer rebasing
   the contributor's commits does not reset the clock.
3. **Maintainer-court skip.** If the contributor has responded but no
   maintainer (``OWNER``, ``MEMBER`` or ``COLLABORATOR``) has submitted a
   review since, the PR is skipped - the ball is in the maintainer's
   court. Comments are not reviews.
4. **Action by days inactive:**

   - **7-13 days:** posts a stale-warning comment.
   - **≥ 14 days:** adds the ``stale`` label and unassigns the contributor
     from linked issues. Any subsequent author activity (push or comment)
     unwinds the label and reassigns linked issues on the next daily run;
     an author comment also triggers the immediate recovery bot.
   - **≥ 60 days:** posts a final follow-up comment asking whether the
     contributor is still working on it. The PR is not auto-closed;
     maintainers may close manually if needed.

   Each stage posts at most once per blocking review cycle.

Secrets
+++++++

These secrets let the reusable workflow mint two GitHub App tokens with
``actions/create-github-app-token``. A repository-scoped write token is
passed to the bot as ``GITHUB_TOKEN`` for issue assignment, labels,
comments, and PR closure. A separate read-only validation token, scoped to
the approved public repositories, is passed as ``VALIDATION_GITHUB_TOKEN``
to validate linked issues and project assignments. The caller workflow's
ambient token is not used for these mutations.

- ``OPENWISP_BOT_APP_ID`` (required): OpenWISP Bot GitHub App ID.
- ``OPENWISP_BOT_PRIVATE_KEY`` (required): OpenWISP Bot GitHub App private
  key.

The OpenWISP Bot needs **Projects: Read** permission at the org level to
check issue project assignments via GraphQL. Without it, valid external
PRs might be wrongly flagged as ``invalid``.

Setup for Other Repositories
++++++++++++++++++++++++++++

.. note::

    Both jobs in the PR reopen workflow use ``bot_command: pr_reopen``.
    The ``pr_reopen`` command dispatches to ``PRReopenBot`` on
    ``pull_request_target`` events (to reassign issues when a PR is
    reopened) and to ``PRActivityBot`` on ``issue_comment`` events (to
    remove the stale label when the PR author comments on their stale PR).

To enable the auto-assignment bot in another OpenWISP repository, see
these caller workflows in ``openwisp-utils``:

- `Issue assignment
  <https://github.com/openwisp/openwisp-utils/blob/master/.github/workflows/bot-autoassign-issue.yml>`_
- `PR issue link
  <https://github.com/openwisp/openwisp-utils/blob/master/.github/workflows/bot-autoassign-pr-issue-link.yml>`_
- `PR reopen
  <https://github.com/openwisp/openwisp-utils/blob/master/.github/workflows/bot-autoassign-pr-reopen.yml>`_
- `Stale PR management
  <https://github.com/openwisp/openwisp-utils/blob/master/.github/workflows/bot-autoassign-stale-pr.yml>`_

They call the `reusable auto-assignment workflow
<.github/workflows/reusable-bot-autoassign.yml>`_, which handles token
generation, environment setup, and execution. When adapting a caller,
change the repository guard and choose a suitable pinned revision of the
reusable workflow.

Overriding the bot username
+++++++++++++++++++++++++++

All four caller workflows accept an optional ``bot_username`` input
(default ``openwisp-companion``). The bot uses it to detect mentions of
the form ``@<bot_username> assign`` in issue comments and to ignore
comments authored by the bot itself. Set this input in each caller job if
your repository uses a different GitHub App username.

GitHub Workflows
----------------

Replicate Commits to Version Branch
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This re-usable workflow replicates commits from the ``master`` branch to a
version branch. The version branch name is derived from the version of the
Python package specified in the workflow.

Version branches are essential during development to ensure that each
OpenWISP module depends on compatible versions of its OpenWISP
dependencies. Without version branches, modules depending on the
``master`` branch of other modules may encounter errors, as the ``master``
branch could include future changes that are incompatible with previous
versions. This makes it impossible to build a specific commit reliably
after such changes.

To address this, we use version branches so that each module can depend on
a compatible version of its dependencies during development. Managing
these version branches manually is time-consuming, which is why this
re-usable GitHub workflow automates the process of keeping version
branches synchronized with the ``master`` branch.

.. note::

    The caller must pass the ``client_id`` input and ``private_key``
    secret for the `OpenWISP Companion bot
    <https://github.com/apps/openwisp-companion>`_, normally mapped from
    its ``OPENWISP_BOT_CLIENT_ID`` organization variable and
    ``OPENWISP_BOT_PRIVATE_KEY`` secret. The OpenWISP GitHub App needs
    **Contents: write** and **Workflows: write** permissions: the latter
    is needed when a synchronized commit changes ``.github/workflows/``.

Call the `reusable version branch workflow
<.github/workflows/reusable-version-branch.yml>`_ from a workflow
triggered by pushes to ``master``. Set ``module_name`` to the Python
module whose version should be used and set ``install_package`` when it
must be installed before importing. Reference the reusable workflow by its
full repository path and a pinned revision. See the `openwisp-utils caller
<https://github.com/openwisp/openwisp-utils/blob/master/.github/workflows/version-branch.yml>`_
for an example.

The workflow creates a missing version branch or fast-forwards an existing
branch to the triggering ``master`` commit. It never rewrites history or
creates merge commits. If the branches diverge, the workflow fails instead
of force-pushing the protected version branch.

If ``master`` is force-pushed intentionally, first verify that the version
branch has no commits which must be retained. Temporarily add the
maintainer performing the recovery to the pull-request and
history-protection ruleset bypass lists, then reset the derived version
branch with an explicit lease. The push fails if the remote version branch
changes after it is fetched:

.. code-block:: bash

    VERSION=<version-number> # e.g. 1.2
    git fetch origin
    git log --oneline origin/master..origin/$VERSION
    EXPECTED_SHA=$(git rev-parse origin/$VERSION)
    git checkout -B $VERSION origin/master
    git push \
      --force-with-lease=refs/heads/$VERSION:$EXPECTED_SHA \
      origin $VERSION

Remove both temporary bypasses immediately after the update.

Backport Fixes to Stable Branch
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This re-usable workflow automates cherry-picking fixes from ``master`` or
``main`` to stable release branches.

It supports two triggers:

- **Commit message**: Add ``[backport X.Y]`` or ``[backport: X.Y]`` to the
  squash merge commit body to automatically backport when merged to
  ``master`` or ``main``.
- **Comment**: Comment ``/backport X.Y`` on a merged PR (org members
  only).

When a cherry-pick conflicts and the commit came from a PR, the bot posts
manual resolution steps on that PR. A missing target branch fails the
backport job. The workflow skips requests for PRs that are not yet merged.

See the `reusable backport workflow
<.github/workflows/reusable-backport.yml>`_ for its inputs and secrets.
The `openwisp-utils backport caller
<https://github.com/openwisp/openwisp-utils/blob/master/.github/workflows/backport.yml>`_
shows a cross-repository call.

Automated CI Failure Bot
~~~~~~~~~~~~~~~~~~~~~~~~

To assist contributors with debugging, this reusable workflow leverages
Google's Gemini API to analyze continuous integration failures in
real-time. Upon detecting a failed CI run, it fetches the pull request
diff through the GitHub API without checking out untrusted pull request
code. It includes changed lines from supported source files alongside the
raw error logs, then posts a concise summary and an actionable remediation
plan directly to the Pull Request.

Pass the failed run's base SHA as ``base_sha`` to analyze its pull request
diff. When it is unavailable, the reusable workflow falls back to the
current pull request base. If it cannot fetch a diff, analysis continues
without source context.

When the bot detects that all failures are transient (e.g., network
errors, browser crashes, Coveralls flakiness), it automatically re-runs
the failed jobs up to 3 times and posts a short notification instead of
the full analysis. The GitHub App token requires **Actions: write**
permission to retry failed jobs. If the retry request fails, the bot posts
the full analysis instead.

Retry mode configuration
++++++++++++++++++++++++

The bot supports a configurable retry classifier mode via
``CI_RETRY_MODE`` (repository or organization variable). Accepted values:

- ``llm`` (default): uses the LLM decision; if the LLM fails, falls back
  to heuristic transient detection.
- ``both``: retries when either heuristic or LLM indicates transient; the
  LLM call is skipped when the heuristic already matched.
- Any other value (including empty/typo): heuristic-only retry.

Model configuration
+++++++++++++++++++

By default the bot uses ``gemini-3.5-flash-lite`` with minimal thinking.
To use a different Gemini 3.5 or later model, set the ``GEMINI_MODEL``
repository or organization variable. An unset or empty value keeps the
default. The same variable also controls the changelog bot, so setting it
once at the organization level changes the model for both bots at the same
time.

This workflow is intended to be triggered via the ``workflow_run`` event
after your primary test suite concludes. It features strict
cross-repository concurrency locks and token limits to prevent PR spam on
rapid, consecutive commits.

Usage Example
+++++++++++++

See the `reusable CI failure workflow
<.github/workflows/reusable-bot-ci-failure.yml>`_ and the `openwisp-utils
CI failure caller
<https://github.com/openwisp/openwisp-utils/blob/master/.github/workflows/bot-ci-failure.yml>`_
for an example. When adapting the caller, set the repository guard and CI
workflow name for your repository and choose a suitable pinned revision.

Changelog Bot
~~~~~~~~~~~~~

This workflow automatically generates changelog entry suggestions for Pull
Requests using Google Gemini. It gets triggered when a PR with a title
prefixed with ``[feature]``, ``[fix]``, ``[change]``, or ``[change!]`` is
approved by a maintainer. ``[change!]`` marks backward incompatible
changes. The bot analyzes the PR's title, description, code changes, and
linked issues, then posts a properly formatted changelog entry as a
comment on the PR.

The bot uses a two-workflow pattern to support PRs from forks. The first
workflow is triggered by ``pull_request_review``: it checks whether the PR
qualifies and uploads the PR number as an artifact, but requires no
secrets. The second workflow executes via ``workflow_run`` once the first
completes: it runs in the context of the base repository, has full access
to secrets, and is the one that generates and posts the changelog comment.

The trigger and runner use the scripts in
``.github/actions/bot-changelog-generator/caller/``. The generator itself
is in ``.github/actions/bot-changelog-generator/shared/`` and is also used
by the composite action.

Secrets
+++++++

- ``GEMINI_API_KEY`` (required): Google Gemini API key.
- ``OPENWISP_BOT_APP_ID`` (required): OpenWISP Bot GitHub App ID.
- ``OPENWISP_BOT_PRIVATE_KEY`` (required): OpenWISP Bot GitHub App private
  key.

Model configuration
+++++++++++++++++++

The changelog bot uses ``gemini-3.5-flash-lite`` with minimal thinking by
default and honors the same ``GEMINI_MODEL`` repository or organization
variable as the CI failure bot. Both bots require a Gemini 3.5 or later
model. Setting it once at the organization level changes the model for
both bots at the same time.

The bot normalizes generated commit-message body text locally before
validation, wrapping long body lines while preserving issue footers such
as ``Closes #123``. This avoids spending extra Gemini requests on
formatting issues that can be fixed deterministically.

Setup for Other Repositories
++++++++++++++++++++++++++++

.. note::

    The trigger workflow name must be ``Changelog Bot Trigger``. The
    runner watches for this name via ``workflow_run``. Changing it will
    silently break the connection between the two workflows.

    Both ``bot-changelog-trigger.yml`` and ``bot-changelog-runner.yml``
    must be committed to the **default branch** of the repository. GitHub
    only activates ``workflow_run`` listeners that exist on the default
    branch: adding the runner only to a feature branch will cause it to
    silently do nothing.

To enable the changelog bot in another OpenWISP repository, see the
openwisp-utils `trigger
<https://github.com/openwisp/openwisp-utils/blob/master/.github/workflows/bot-changelog-trigger.yml>`_
and `runner
<https://github.com/openwisp/openwisp-utils/blob/master/.github/workflows/bot-changelog-runner.yml>`_
workflows. Adapt their repository guards and use a suitable pinned
revision for the changelog generator.

The trigger workflow runs when a PR review is submitted. If the PR is
approved by a maintainer and its title starts with ``[feature]``,
``[fix]``, ``[change]``, or ``[change!]``, it stores the PR number as
workflow metadata.

The runner workflow is triggered after the trigger workflow completes. It
validates the metadata against the triggering run and checks that an
eligible reviewer approved the current PR head. Only then does it prepare
the approved diff and generate a changelog entry using secrets.

On-Demand AI Review
~~~~~~~~~~~~~~~~~~~

This reusable workflow lets OpenWISP organization members request an AI
review by commenting on a pull request:

1. ``/review``: checks whether the pull request is worth the effort (root
   cause or workaround, approach, ``AGENTS.md`` rules, performance and
   race conditions). When an important design choice depends on missing
   context or maintainer priorities, it explains the options and asks for
   a maintainer decision. Using the `OpenWISP Threat Model
   <https://github.com/openwisp/openwisp-docs/blob/master/security/threat-model.rst>`_,
   it also states whether the change affects the security perimeter and
   recommends ``/security-review`` or ``/final-review`` next.
2. ``/security-review``: looks for actionable security issues.
3. ``/final-review``: checks whether earlier findings were addressed and
   looks for new critical issues, including significant violations of
   base-branch ``AGENTS.md`` rules. A complete review can approve when no
   findings are outstanding and no material question remains. Relevant
   testing limitations appear separately under ``Verification`` and do not
   alone prevent approval. A gap that could change the verdict remains
   ``Unclear`` and makes the review inconclusive. Required CI checks still
   govern whether the pull request can merge.

Before running any command, every review checks the pull request for
prompt injection and attempts to steal secrets, and if it finds one it
stops and requests changes with the evidence.

The OpenWISP bot publishes the review with a verdict, a summary and inline
comments labeled ``P1`` to ``P3``. A ``Maintainer decision needed``
verdict is posted as a comment and keeps earlier change requests of the
same stage. Conclusive reviews dismiss earlier change requests of the same
stage. To verify its findings, the model can search the web, fetch pages,
edit a temporary copy of the pull request and run allowed commands, such
as tests. Commands run as a separate user that cannot read the model
credentials, and the model has no access to the workflow's GitHub tokens.
Pull request content, tool output and fetched pages are treated as
untrusted data. Each review also reads the pull request title, description
and discussion, and the OpenWISP issues linked in the description, as
data. The writing and review rules shared by OpenWISP AI tools are read by
the OpenWISP bot from the ``AGENTS.md`` of `openwisp-opencode-configs
<https://github.com/openwisp/openwisp-opencode-configs>`_; if a section is
missing, the review notes it in its summary. Each review is limited to 50
minutes, and the model is told about the limit so it replies in time.

CI-aware reviews
++++++++++++++++

To opt in, use ``.github/workflows/ci.yml`` for primary CI and follow the
`example caller <.github/workflows/bot-ai-review.yml>`_ for
``wait_for_ci`` and the completion trigger. The GitHub App needs Actions
read and pull request write permissions.

With opt-in, reviews wait for CI to finish, not to pass. If the bot cannot
use the run, it says why; request a new review once CI is available.
Completion scans and failed-log collection have resource limits. If a
waiting review does not resume, check the completion workflow and request
the review again. Without opt-in, reviews run without waiting and say CI
was not checked. If a review reports missing CI files, see `CI
standardization (#39)
<https://github.com/openwisp/openwisp-actions/issues/39>`_.

Review flow
+++++++++++

The `reusable AI review workflow
<.github/workflows/reusable-bot-ai-review.yml>`_ runs these jobs:

.. code-block:: mermaid

    flowchart LR
      C["Member requests a review"] --> G["Gate: check command and membership, read PR and guidance"]
      G --> A["Acknowledge: add eyes reaction"]
      G --> R["Review: fetch PR data and run the model in a sandbox"]
      R --> F["Upload findings.json"]
      F --> P["Publish review and dismiss superseded change requests"]
      A --> X["React: rocket or confused"]
      R --> X
      P --> X

The final reaction is updated after the review and publish jobs finish, if
the acknowledgement added an eyes reaction. The review job passes its
findings to the publish job as an artifact.

Implementation layout
+++++++++++++++++++++

The implementation is in ``.github/actions/bot-ai-review/``:

- ``reusable/`` contains the workflow step scripts and sandbox helpers.
- ``prompts/shared/`` contains prompt parts used by every review.
- ``prompts/stages/`` contains the prompt for each review stage.
- ``opencode.json`` defines tool permissions and allowed commands.
- ``tests/`` contains tests for the review scripts.

The review job keeps the PR diff and other model inputs in
``/tmp/ai-review/data/``, outside the PR copy in ``/tmp/ai-review/pr/``.
It writes ``findings.json`` under ``$RUNNER_TEMP`` and uploads it for the
publish job.

Prompt and sandbox
++++++++++++++++++

The review prompt combines these parts in order:

1. ``prompts/shared/context.md``, with the time limit filled in.
2. ``prompts/stages/<n>-<stage>.md`` for the selected review stage.
3. The shared AI guidance from ``openwisp-opencode-configs``.
4. ``prompts/shared/verification.md``.

The model reads and edits ``/tmp/ai-review/pr/``. Shell commands run as
the separate ``reviewer`` user, without ``sudo``, in
``/tmp/ai-review/run/``. Before each command, the model's edits are
synchronized to the command copy and files deleted from the model's copy
are removed. Files generated by commands are not copied back to the
model's copy.

Repositories can opt into CI dependency reuse by calling an executable
``./install-ci-deps.sh`` in the ``test`` job's ``deps`` step. In a matrix,
mark one row with ``review_default: true``. Declare required browsers with
``AI_REVIEW_BROWSERS``. See the `review workflow
<.github/workflows/reusable-bot-ai-review.yml>`_ and `CI cache action
<.github/actions/ci-cache/action.yml>`_ for the supported settings.
Without standardized CI, reviews continue without dependency setup. The
installer receives ``CI=true`` and direct matrix references in the test
job and dependency step environment. Other expressions are not evaluated.
If a ``django-version`` axis is present, it takes precedence over a
``DJANGO_VERSION`` value from another axis. An installer can create a
virtual environment at the repository root as ``.venv``. Review commands
use its Python and installed dependencies.

The unprivileged installer and review commands require Linux Landlock ABI
3 or newer. The workflow refuses to start either process if it cannot
restrict file writes to the reviewer home and working copy. Use ``TMPDIR``
for scratch files. The runner's toolchain stays available on ``PATH`` but
is not writable by these processes.

For privileged host dependencies, set ``AI_REVIEW_SYSTEM_DEPS: "true"`` in
the test job environment and follow the `installer phase contract
<.github/actions/ci-dependencies/reusable/prepare_review.sh>`_. Additional
caches use ``AI_REVIEW_CACHE_GLOB`` and, when needed,
``AI_REVIEW_CACHE_AXES``. Privileged setup must use trusted base-branch
code, not pull request code. Services, builds, and tests remain separate
from installation. The ``./runtests`` entry point must allowlist reviewed
test flags; argument validation does not sandbox untrusted test code or
configuration.

To run the AI review tests from the repository root:

.. code-block:: shell

    python -m pytest .github/actions/bot-ai-review/tests -q

Model configuration
+++++++++++++++++++

The provider and models come from these Actions variables:

- ``OPENCODE_PROVIDER``: the provider, e.g. ``github-copilot``.
- ``AI_REVIEW1_GENERAL_MODEL``: the model for ``/review``.
- ``AI_REVIEW2_SECURITY_MODEL``: the model for ``/security-review``.
- ``AI_REVIEW3_FINAL_MODEL``: the model for ``/final-review``.
- ``AI_REVIEW1_GENERAL_EFFORT``: optional reasoning effort for
  ``/review``.
- ``AI_REVIEW2_SECURITY_EFFORT``: optional reasoning effort for
  ``/security-review``.
- ``AI_REVIEW3_FINAL_EFFORT``: optional reasoning effort for
  ``/final-review``.

Set them as organization variables to apply to all repositories. A
repository variable with the same name overrides the organization one,
e.g. to use a stronger security model in a critical repository. If the
provider or the model of a review is unset, the review fails with an error
and the comment gets a confused reaction. With ``github-copilot``, pass
the Copilot token as the ``OPENCODE_AUTH`` secret. Each review states the
provider and model it used.

Effort values are OpenCode model variants. Leave an effort variable unset
to use the current OpenCode and provider defaults. The highest available
value may be ``high``, ``xhigh`` or ``max``, depending on the provider and
model. To check, run ``opencode models <provider> --verbose`` with that
provider configured and look for the model's ``variants``. See the
`OpenCode model variants documentation
<https://opencode.ai/docs/models/#variants>`_. An unsupported effort
causes the review to fail rather than silently using the default. To find
the configured effort, check the repository's Actions variables, then the
organization variables. The review does not report the effective effort
when the variable is unset.

Usage Example
+++++++++++++

See the `openwisp-utils AI review caller
<https://github.com/openwisp/openwisp-utils/blob/master/.github/workflows/bot-ai-review.yml>`_
for a cross-repository example.

Development
===========

From the repository root on Linux, with Bash, Git, jq, ``yq`` v4, rsync,
flock, OpenSSL, and Prettier available:

.. code-block:: shell

    python3.13 -m venv .venv
    source .venv/bin/activate
    python -m pip install -r requirements-test.txt
    ./run-qa-checks
    ./runtests

For a focused run, pass a test file such as
``.github/actions/ci-dependencies/tests/test_detect_ci.py`` to
``./runtests``.

Run ``./qa-format`` to apply the shared OpenWISP formatting before QA.

Contributing
============

Please read the `OpenWISP Contributing Guidelines
<https://openwisp.io/docs/dev/developer/contributing.html>`_.

Support
=======

See `OpenWISP Support Channels <https://openwisp.org/support.html>`_.

Changelog
=========

See `CHANGES.rst
<https://github.com/openwisp/openwisp-actions/blob/master/CHANGES.rst>`_.

License
=======

See `LICENSE
<https://github.com/openwisp/openwisp-actions/blob/master/LICENSE>`_.
