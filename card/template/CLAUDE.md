## Shared by every card

This section, the workflows and the release tools are the same in every Home Assistant dashboard
card of the owner. They come from `HairingX/workflows`: the workflows in `.github/` are copies of
its template, which call its reusable workflows and actions at `@v2`, and this section is a copy
of its `card/template/CLAUDE.md`. The tests check that the copies agree; a change to any of them
is made there, released, and synced into every repository with its
`common/tools/template.py sync card`. What is this repository's own is above this section.

## Comments and TSDoc

Based on the TSDoc standard and the Google TypeScript Style Guide (Comments and documentation),
held to the rules the owner's Python repositories follow for docstrings.

**TSDoc describes the unit's own contract, and nothing else.**
- Every exported module, class, function, method, property, type and constant has a `/** */`
  comment; a module's is a `@packageDocumentation` comment at its top.
- The first sentence is a one-sentence summary. Add more only when a caller needs it:
  parameters, return value, errors thrown, events fired, side effects, invariants.
- Use `@param`, `@returns` and `@throws` only when they say something the signature does not.
  Never repeat types; TypeScript carries them.
- Describe what the unit does, not who calls it, how other classes use its data, or where its
  result ends up. That knowledge belongs to those other units and goes stale here.

**Comments explain why, never what.**
- Write one only where the code cannot say it: a quirk of Home Assistant's frontend or of a
  browser, a non-obvious constraint, the reason for an order of operations.
- No history: no "used to", "previously", "the old code", "this was a bug". Version control
  holds history; a regression test's name holds the reason it exists.
- No references to other files, classes, line numbers or design-document sections. They rot the
  moment the other side changes.
- No commented-out code. No TODO without an issue reference.

**Keep them short.** A comment longer than a few lines is design rationale; it belongs in
`docs/`, where it can cover several modules at once.

**Tests.** The test name states the behaviour. Add a comment only when the reason is not
obvious from the name - one or two lines, no narrative.

## Conventions

- All documentation, comments and commit messages are in English.
- The card is TypeScript and lit, in `src/`, bundled by vite in library mode into one ES module,
  `dist/<filename>`, `<filename>` being `hacs.json`'s `filename`. `dist/` is built, never
  committed, and in `.gitignore`.
- npm, on the newest Node LTS, installs exactly what the committed `package-lock.json` locks:
  `npm ci`.
- The scripts the tests run: `npm run lint` (eslint, and prettier's check), `npm run typecheck`
  (`tsc --noEmit`, strict), `npm test` (vitest with happy-dom) and `npm run build`. The build
  embeds the version the environment variable `CARD_VERSION` gives it, `0.0.0` without one.
- TypeScript is strict and reports 0 errors, as does eslint: no `@ts-ignore`, `@ts-expect-error`,
  `@ts-nocheck`, `eslint-disable` or `any`, and no rule turned off. Where Home Assistant's
  frontend gives no types, declare the part the card uses, narrowed from `unknown`.
- The tests are vitest, beside the code they test or in `tests/`, and cover every line, branch,
  function and statement of the card; the build fails below 100%, whatever the repository's own
  configuration says.
- Every problem found gets a test that fails without the fix.
- `hacs.json` names the card (`name`), its bundle (`filename`) and the oldest Home Assistant it
  supports (`homeassistant`); the tests check it.
- No real IP addresses, hostnames, serial numbers, email addresses or credentials in tracked
  files. Examples use the documentation ranges, such as 192.0.2.0/24.

## Keeping up with Home Assistant

Best practice is what Home Assistant and HACS require and recommend now; it moves with every
release. After any change to the card or to the packages it uses:

1. Read the Home Assistant developer blog since the last check for changes to the frontend and
   to custom cards, and raise `homeassistant` in `hacs.json` when the card needs something newer.
2. Read HACS's publishing requirements for dashboard repositories again.
3. Try the card on a real Home Assistant with a test build.

## Releasing

**`package.json` in the repository always says `0.0.0`, and the draft release is never
published by hand.** HACS installs the bundle a release carries, as the asset `hacs.json`'s
`filename` names, and only Release builds it: it embeds the release's version in the bundle on
the runner, and refuses a bundle that does not hold that version. Nothing is committed by a
release: the tested commit is tagged, and the version exists only in the tag and the bundle.

1. Merge pull requests into `main`. Release Drafter keeps a draft release proposing the next
   version: a minor bump for the label `breaking-change` or `minor`, a patch otherwise.
   **A new major version is never worked out**, as a label placed wrongly must not release one;
   type it into Release as the override.
2. Wait until the Release Drafter run on `main` has finished. Release refuses a draft that is not
   up to date with `main`.
3. Show the maintainer the draft's notes and its version, and get explicit approval before
   running Release.
4. Run the **Release** workflow from the Actions tab, on `main`, and choose **release
   candidate** or **final release**. It works out the version: the next release candidate of the
   open series (`0.2.0rc1` -> `0.2.0rc2`), or the final release that ends it (`0.2.0`); a draft
   naming a higher version starts a new series. Type a version only for a new major, or to
   override one worked out wrongly: canonical PEP 440, of the kind chosen.

Release refuses any version not higher than every version released, and a version with no pull
request merged since the release before it - for a final release, the final release before it.
It runs the tests and the HACS validation on the exact commit it releases, builds the bundle from
that commit with the version embedded and checks it, tags that commit, and publishes the GitHub
release with the bundle, marked as a pre-release where it is one; HACS offers a pre-release only
to those who switch beta versions on, and then the newest one.

HACS installs a card from the newest final release's assets, so it finds none before the first
final release: until then, its validation is skipped with a notice.

A release candidate's notes are written by GitHub from the pull requests merged since the
previous release candidate or final release, grouped by label as `.github/release.yml` says, and
the draft is kept. A final release's notes are the draft's - the first final release says only
that it is the initial release - and the final release deletes the draft. To change what a
release says, change the pull requests: the title is the line, the labels decide the section.

If publishing fails part-way, **Re-run failed jobs** resumes it: it accepts the tag it pushed on
the same commit, removes a draft an interrupted upload left behind, and uploads the bundle to the
release it already created. **Re-run all jobs** is refused once the version is tagged.

Actions are referred to by their major version where they publish one. Dependabot proposes each update of the npm packages once it is three days old, all
that are no new major version in one pull request a week, and **Merge Dependabot's updates**
merges it once every check passes, then updates the release draft. It assigns the owner only an
update that needs them: a new major version, or one a check fails. The actions are the
template's, kept up to date in HairingX/workflows.

## Testing a branch on a real Home Assistant

HACS installs only releases, pre-releases and the default branch. To try a development branch
on a real Home Assistant, run the **Test build** workflow from the Actions tab on that branch:

1. It tests and validates the branch's commit, then publishes it as a pre-release such as
   `v0.1.0b3`: the next release's version - the draft's, or the patch after the last release
   when there is no draft - with the first free `b<n>`. The branch's commit is tagged; the
   version is set only in the bundle the pre-release carries.
2. In Home Assistant, switch beta versions on for this repository in HACS, and install the test
   build; HACS updates the dashboard resource, so a reload of the browser loads it. Switch beta
   versions off and install the latest release to go back.

A new test build of a branch replaces its previous one, and closing the branch's pull request or
deleting the branch removes them. Test builds never count as releases.

## Branches and pull requests

- Every change goes through a branch and a pull request: `main` takes no push. The ruleset in
  `.github/rulesets/main.json` enforces it, with the checks "Tests and type check" and "HACS"
  required; its only bypass is the owner's, and only for merging a pull request. A change to
  what a user gets - the card's code or documentation - comes with its tests.
- Name every branch by the kind of change, as the release draft's labels follow the name;
  `.github/rulesets/branch-names.json` refuses any other name. `feature/<what>` is labelled
  `feature request`, `fix/<what>` is labelled `bug`, `docs/<what>` is labelled `documentation`,
  and `chore/<what>` - CI, tooling, anything that stays in the repository - is labelled `chore`.
  The release notes list features and fixes; documentation, chores and Dependabot's
  `dependencies` are left out. A change to what a user installs, such as a new package the
  bundle includes, is a `fix/` or a `feature/`, never a `chore/`.
- A pull request's text describes only its own change: what it does and how it was tested. Never
  releases to come, merge order, or other repositories.
- Put `breaking-change` on a pull request that breaks the card's configuration - a `feature/` or
  `fix/` one, as a chore is left out of the notes - and `minor` on one that needs a minor bump;
  both give a minor bump, and a patch is the default. No label gives a major.
