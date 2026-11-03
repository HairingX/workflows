# Conventions for this repository

The workflows, actions and release tools every repository of the owner shares - the Home
Assistant integrations, the Python libraries they use, and the Home Assistant dashboard cards -
and the templates of the files each of them keeps a copy of. How and why it is built as it is:
`docs/design.md`.

## What lives here

- `common/`: what every kind of repository shares.
  - `common/tools/`: the version rules (`release_version.py`), what becomes of Dependabot's
    updates (`dependabot.py`), what a repository says about itself under
    `[tool.hairingx-workflows]` in its `pyproject.toml` (`settings.py`), the libraries taken from
    a branch (`libraries.py`), the template check and sync (`template.py check|sync KIND ROOT`),
    and the jq filter that finds a branch's test builds (`branch_test_builds.jq`).
  - `common/release-drafter.yml`: Release Drafter's configuration.
  - `common/template/`: the files every repository keeps word for word: the release-notes
    categories, the branch-names ruleset, and the Release Drafter, inactive-issues and
    Dependabot-merge workflows.
- `ha/`: the Home Assistant integrations'.
  - `ha/actions/tests`, `ha/actions/libraries-released`: composite actions, used by the
    integrations' workflows at `@v2` and by the reusable workflows from their own commit.
  - `ha/tools/`: the scripts only integrations need. They read what differs between
    integrations from the integration's own files - the domain from `custom_components/`, the
    zip from `hacs.json` - and never name one.
  - `ha/template/`: the files every integration keeps besides the common ones, and
    `ha/template/CLAUDE.md`, the shared section of its CLAUDE.md.
- `python/`: the Python libraries', laid out the same: `python/actions/`, `python/tools/` (the
  package's names, and the library's contract) and `python/template/`. A library publishes to
  PyPI from its own Release workflow, as PyPI's trusted publishing takes no reusable workflow.
- `card/`: the dashboard cards', TypeScript bundled into one ES module that HACS installs from a
  release's assets: `card/actions/tests` and `card/actions/hacs`, `card/tools/` (the bundle and
  the card's contract) and `card/template/`, with `card/template/CLAUDE.md`.
- `.github/workflows/`: the reusable workflows, prefixed by the kind they serve -
  `ha-release.yml`, `ha-test-build.yml`, `ha-test-build-cleanup.yml`, `ha-harness-merge.yml`,
  `python-release.yml`, `python-github-release.yml`, `card-release.yml`, `card-test-build.yml` -
  and `release-drafter.yml`, `test-build-cleanup.yml` and `dependabot-merge.yml`, shared by
  every kind. GitHub finds a reusable workflow only directly in that directory. Each checks out
  this repository at its own commit (`job.workflow_repository`, `job.workflow_sha`) for its
  tools. `ci.yml`, `publish.yml` and `merge-dependabot.yml` are this repository's own.
- `tests/`: `tests/common/`, `tests/ha/`, `tests/python/`, `tests/card/`, and
  `tests/test_workflows.py` for every workflow and action.

## Changing anything

1. Change it here, with its test, through a pull request. CI runs the tests, pyright strict, and
   actionlint with shellcheck on every workflow and every action's script, and the canary: the
   change's shared tests on `main` of `ha_duka_connect`, `event_connect` and
   `ha_aula_connect_card`. A canary fails only where the published actions pass that
   repository; where they fail too, it warns that the repository itself is broken. Dependabot's
   updates here are merged once every check passes.
2. Publish it: run **Publish** on `main` with the next version. It runs CI and the canary on the
   commit, tags it and moves the major tag to it, so every repository uses it from its next run;
   a new major version is published without the canary. There is one version for every kind.
3. A change to a template turns the tests of every repository that keeps it red until its
   copies are synced: open a pull request in each with `common/tools/template.py sync KIND`. A
   change the copies must follow at the same moment - an input added to a reusable workflow, or
   a path moved - is a new major version, published while the repositories stay at the major
   before until each is synced.

The comments, docstrings, tests and branch conventions are the repositories' own, in
`ha/template/CLAUDE.md`, `python/template/CLAUDE.md` and `card/template/CLAUDE.md`. Python 3.14;
pyright strict reports 0 errors, with no `# type: ignore`.
