# Design

## Why one repository

Six integrations - Aula, Duka Connect, Nilan Connect, Wavin Sentio Connect, PowerView Connect
and Charge Smarter - shared their release flow by copying it. The copies drifted, and a defect
found in one stayed in the others. Here the logic exists once; each integration keeps only small,
identical files that call it, and its tests fail when those files differ from the template.

The Python libraries the integrations use share most of it: the versions, release candidates,
Release Drafter, branch names and release notes, and so do the dashboard cards. So every kind of
repository is served from this one repository, with one version:

- `common/`: what every kind shares - the version rules (`common/tools/release_version.py`),
  Release Drafter's configuration, and the template files every repository keeps
  (`common/template/`: the release-notes categories and the branch-names ruleset).
- `ha/`: the Home Assistant integrations' actions, tools and template.
- `python/`: the Python libraries'. A library's Release is the integrations' Release with a
  package instead of a zip: setuptools-scm works the version out from the tag, so the tag is
  made before the build and pushed only once the built package says that version. PyPI's
  trusted publishing takes no reusable workflow (it is bound to the repository's own workflow
  file), so the library's `release.yml` calls the shared release, uploads to PyPI itself, and
  calls the shared GitHub release after.
- `card/`: the Home Assistant dashboard cards'. A card's Release is the integrations' Release
  with a bundle instead of a zip: one ES module, built with the version embedded and attached to
  the release, from where HACS installs it.
- `.github/workflows/`: the reusable workflows, prefixed by kind (`ha-release.yml`), or by none
  when every kind shares them (`release-drafter.yml`, `test-build-cleanup.yml`); GitHub finds a
  reusable workflow only directly in that directory, never in a subdirectory.

One version (`vX.Y.Z`, and the major `vX` the callers use) rather than one per kind: GitHub,
Dependabot and the other tools of Actions expect a repository's tags to be its versions. A change
that breaks one kind's callers is a new major for all; as every repository keeps the template's
files, it only changes the major the next sync writes.

## How an integration calls it

GitHub's own mechanism for CI shared between repositories:

- **Reusable workflows** (`on: workflow_call`) for whole flows: Release, Test build, Test build
  cleanup, Release Drafter. The integration's workflow file holds the trigger, the inputs, the
  concurrency group and the token's permissions, and calls `...@v2`. A called workflow cannot
  raise the permissions its caller grants.
- **Composite actions** for steps a required check runs: `ha/actions/tests` and
  `ha/actions/libraries-released`. A ruleset requires a check by its name, and a job called through
  a reusable workflow is named `<caller job> / <job>`; a job of the integration's own workflow
  that uses an action keeps the name the rulesets require ("Tests and type check", "Libraries
  released and pinned"). Hassfest and HACS are a single step each, called directly.
- A reusable workflow needs its tools at its own version. `uses:` takes no expressions, so it
  checks this repository out at `job.workflow_repository` / `job.workflow_sha` - GitHub's job
  context names the repository and commit of the workflow file that defines the job - into
  `.workflows`, and uses the actions from there by path. Release Drafter reads its
  configuration from the same commit (`config-name: owner/repo:/path@sha`). The only inputs a
  `workflow_call` takes are strings, numbers and booleans; the choice of release candidate or
  final release is a choice input of the caller, passed on as a string.
- `@v2` is a major tag, moved by Publish; this follows the integrations' rule of referring to
  actions by their major version.

## What differs between integrations, and where it is read

Nothing here names an integration. The domain is the one directory under `custom_components/`,
which its manifest must name; the zip is `hacs.json`'s `filename`; the libraries developed
alongside it, taken from their branch of the same name on a development branch, are listed in
install order under `[tool.hairingx-workflows]` in `pyproject.toml`. Everything else -
code, tests, manifest pins, `requirements-test.txt`, `quality_scale.yaml`, README, the top of
CLAUDE.md - is the integration's own.

## Release flow

Ported from the integrations' flow and from Aula's review of it, with these defects of the
copies fixed (each has a test):

| Defect in the copies | Fix |
|---|---|
| A release candidate deleted the draft: the final release lost its notes, and test builds failed until the next merge | only a final release deletes the draft |
| A stale test-build tag (`0.3.0b1`) opened a "series" and forced the next release to `0.3.0` | only `rc` tags open a series; test-build tags never bound a release |
| Cleanup matched `test-build-branch: fix/a` as a substring, removing `fix/ab`'s builds | whole-line match in jq; the build being published is never selected |
| The draft was read twice, and only from the first 30 releases | captured once in prepare, from every page; refused unless Release Drafter finished with the very commit and `main` did not move |
| Publishing could not be resumed after the tag push | every publish step is idempotent: the tag is accepted on the same commit, a draft an interrupted upload left is removed, the zip uploaded to the existing release |
| HACS validation checked the branch's tip, not the commit released | `REPOSITORY_REF` set to the commit; the HACS action validates through the API at that ref |
| A re-run could upload the zip to the draft of the same tag | gh looks a release up by tag among drafts too: the draft is deleted before publishing; a published release is found with `releases/tags/{tag}`, which never returns drafts |
| `.dev` and `.post` overrides were accepted, then ignored as tags | refused |
| JSON lines were split on U+2028 inside a pull request title | split on `\n` only |
| Test builds had no version without a draft | the patch after the last final release (from PowerView's copy) |
| A library from a branch was installed over its pin | it takes the pin's place in the requirements (from PowerView's copy) |

Before the first final release, Release Drafter has no published release to compare with: its
draft says "No changes" and warns that it lacks a baseline. The first final release therefore
says only that it is the initial release; every later one carries the draft's notes.

## Checks every integration's tests run

`ha/actions/tests` runs pyright strict, the tests with 100% coverage, `ha/tools/contract.py` and
`common/tools/template.py check ha`. The contract: the manifest says `0.0.0`; `hacs.json` sets
`zip_release`, names the zip after the domain and requires a Home Assistant no newer than the
one the tests run;
the requirements follow hassfest's rules for a custom integration - none Home Assistant itself
installs, a minimum version that admits Home Assistant's for one its own integrations pin, `==`
for any other - and `requirements-test.txt` pins what the tests run (skipped for a library built
from a branch); `quality_scale.yaml` states
every rule hassfest's `ALL_RULES` lists, with a comment for each rule not done; every
translation holds English's keys.

**The oldest Home Assistant supported.** `hacs.json` names the oldest Home Assistant an
integration supports, and the tests hold it to that promise as to the newest: where it is older
than the one the pinned harness is made for, the action installs it in a second environment,
with the harness release pip resolves for it and `requirements-test.txt` rewritten to its own
integrations' pins, and runs pyright, the tests and the requirements' rules again
(`contract.py minimum`, `minimum-requirements`, `minimum-check`). Each environment runs on the
oldest Python its Home Assistant requires on PyPI (`ha/tools/pythons.py`), so a Home Assistant
moving to a newer Python needs no change here. The versions between the two are not tested:
Home Assistant removes what integrations use only after a deprecation period of at least twelve
months, and the tests of the newest fail on any deprecation reported. So an integration need
not require the newest Home Assistant, and Dependabot's update of the harness is merged without
a hand when it passes: `ha-harness-merge.yml` waits for every check of the pull request, merges
the commit tested, and starts Release Drafter, as a merge made with a workflow's token starts no
push run; Release accepts a draft from such a run.

Release and Test build run the same action without the template check: a change to the
template must not stop an urgent release before every integration is synced; pull requests and
pushes still check it, so a repository that differs cannot merge.

A library taken from its branch replaces its pin, rather than being installed over it. When a
released library pins another one, a branch of only the other one may then not resolve: give the
first library a branch of the same name too.

## A dashboard card

A card is TypeScript and lit, bundled by vite into one ES module. What differs between cards is
read from the card's own files: the bundle is `dist/<filename>`, `filename` being `hacs.json`'s;
everything else - code, tests, `package.json`, `package-lock.json`, `hacs.json`, README, the top
of CLAUDE.md - is the card's own. Cards have no libraries developed alongside them, so they keep
no "Libraries released and pinned" check: their packages come from npm, locked.

**The version.** `package.json` says `0.0.0`, as the integrations' manifest does, and the build
embeds the version the environment variable `CARD_VERSION` gives it. Release and Test build build
the bundle with the version they publish and refuse one that does not hold it as a whole word: a
minifier may fold it into a longer string, such as the banner a card logs, so it is not looked for
in quotes.

**Where HACS finds the card.** HACS looks for the file `filename` names first among the assets of
the newest final release (the newest pre-release for those who switch beta versions on), then at
the root of the repository, then in `dist/`. So `dist/` is built, never committed, and the release
attaches the bundle: what a user installs is what Release built and checked. `content_in_root`
would make HACS skip the release's assets, so the contract refuses it.

**HACS validation before the first final release.** HACS refuses a card repository it finds no
bundle in, and with `dist/` uncommitted it finds one only among a final release's assets. The
validation would then fail on every pull request and on the first Release itself, which it must
precede. `card/actions/hacs` therefore runs it only once a final release exists, and says so with
a notice before; the repository's contract checks `hacs.json` meanwhile, and the daily run
validates the rest from the first final release on.

**Install scripts.** npm runs the install scripts of every package it installs. In Release and
Test build, the bundle is built in a job of its own, with a read-only token and no credentials in
its checkout, and handed to the job that tags and publishes as an artifact: no package's script
ever sees a token that can push.

**Checks every card's tests run.** `card/actions/tests` runs `npm ci`, then the card's own
scripts - `lint`, `typecheck`, `test`, `build` - with vitest's coverage thresholds set to 100%
from the command line, whatever the card's configuration says; checks that the build wrote the
bundle; and runs `card/tools/card_contract.py` and `common/tools/template.py check card`. The
contract: `package.json` and `package-lock.json` say `0.0.0`, `package.json` has the four
scripts, `hacs.json` names the card, the bundle and the oldest Home Assistant it supports and
sets neither `zip_release` nor `content_in_root`, and nothing under `dist/` is tracked.

**Test build cleanup.** Removing a branch's test builds knows nothing of the kind, so the cards
call the shared `test-build-cleanup.yml`. The integrations' copies call
`ha-test-build-cleanup.yml` until the next major version moves them; a test holds the two to the
same jobs.

## On the way to the standard

An integration far from the standard - Aula, whose code was written before it - is not left red
while it gets there. `[tool.hairingx-workflows] transition` in its `pyproject.toml` says
why; `coverage` then sets the percentage its tests must reach, and pyright - strict - may leave
the files listed in its `ignore` unchecked. The contract warns on every run while a transition
lasts, and refuses a lower coverage, a pyright mode other than strict, or files left unchecked
without one.
That the floor only rises is a rule of review, not a check.

## Facts relied on, and where they were checked

- `job.workflow_repository` and `job.workflow_sha`: GitHub's contexts reference. actionlint
  1.7.12 does not know them yet, so its check of them is turned off in `.github/actionlint.yaml`.
- Local `./` paths in `uses:` resolve against the workspace, so an action checked out to a
  directory is used by path.
- Release Drafter v7 reads `owner/repo:/path@ref` and ignores pre-releases as the last release
  (`include-pre-releases` defaults to false).
- HACS (`repositories/base.py`): reads the first 30 releases, skips drafts, offers the newest
  pre-release above the newest final one only with beta versions on, and downloads the zip named
  by `filename` when `zip_release` is set. The HACS action reads `REPOSITORY_REF`.
- gh 2.89: `gh release create` with an asset creates a draft, uploads, then publishes; lookups
  by tag consider drafts.
- The quality scale rules equal hassfest's `ALL_RULES` at Home Assistant 2026.10.4.
- HACS (`repositories/plugin.py`, `update_filenames`): a dashboard card's file is the release
  asset `filename` names, in the newest release HACS lists, unless `content_in_root`; else
  `filename` at the root, then in `dist/`. Without one, validation fails with "Repository
  structure ... is not compliant". The HACS action takes `category: plugin` and reads
  `REPOSITORY_REF`, as for an integration; an empty `REPOSITORY_REF` would replace the event's.
- GitHub's `releases/latest` returns the newest release that is neither a draft nor a
  pre-release, as HACS's own choice is without beta versions.
- vitest 5: `--coverage.enabled=true --coverage.thresholds.100=true`, passed after `npm test --`,
  enables coverage and fails the run below 100% of lines, branches, functions and statements,
  whether or not the card's script already says `--coverage`.
