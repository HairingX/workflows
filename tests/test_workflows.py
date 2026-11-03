"""Tests of the workflows, the actions and the templates of the callers."""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

from library_contract import PYTHON_VERSIONS

ROOT = Path(__file__).parents[1]
TEMPLATES = [ROOT / "common/template", ROOT / "ha/template", ROOT / "python/template", ROOT / "card/template"]
CALLERS = sorted(path for template in TEMPLATES for path in (template / ".github/workflows").glob("*.yml"))
WORKFLOWS = sorted([*(ROOT / ".github/workflows").glob("*.yml"), *CALLERS])
ACTIONS = sorted(path for kind in ("ha", "python", "card") for path in (ROOT / kind / "actions").glob("*/action.yml"))
BRANCH_TEST_BUILDS = ROOT / "common" / "tools" / "branch_test_builds.jq"
HA_TESTS = ROOT / "ha/actions/tests/action.yml"
HA_INSTALL = ROOT / "ha/actions/tests/install.sh"
OWN = re.compile(r"uses: HairingX/workflows/([^@\s]+)@(\S+)")
KINDS = ["ha", "python", "card"]
MAJOR = "v2"
"""The major version the callers use, which Publish moves."""

OWN_WORKFLOWS = {"ci.yml", "publish.yml", "merge-dependabot.yml"}
"""This repository's own workflows, which no integration calls."""

SUPERSEDED = {"ha-harness-merge.yml"}
"""Reusable workflows the template no longer calls, kept for copies not yet synced until the next
major version."""

BASH = "defaults:\n  run:\n    shell: bash\n"


def _ids(paths: list[Path]) -> list[str]:
    return [path.relative_to(ROOT).as_posix() for path in paths]


def test_the_workflows_and_actions_are_found() -> None:
    assert len(WORKFLOWS) > 10
    assert len(ACTIONS) == 6


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=_ids(WORKFLOWS))
def test_a_step_fails_when_a_command_piped_into_another_fails(workflow: Path) -> None:
    """GitHub runs a step as `bash -eo pipefail` only when the shell is given; without one it
    runs `bash -e`, where a failing command piped into another fails nothing."""
    assert BASH in workflow.read_text("utf-8")


@pytest.mark.parametrize("path", [*WORKFLOWS, *ACTIONS], ids=_ids([*WORKFLOWS, *ACTIONS]))
def test_no_step_pipes_into_a_command_that_stops_reading(path: Path) -> None:
    """With pipefail, the command before `head` fails when head stops reading its output."""
    assert "| head" not in path.read_text("utf-8")


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=_ids(WORKFLOWS))
def test_every_workflow_states_its_token_permissions(workflow: Path) -> None:
    assert "\npermissions:" in workflow.read_text("utf-8")


@pytest.mark.parametrize("action", ACTIONS, ids=_ids(ACTIONS))
def test_every_step_of_an_action_runs_bash_with_pipefail(action: Path) -> None:
    """A composite action's run step must name its shell, and bash runs it with pipefail."""
    steps = cast(list[dict[str, Any]], yaml.safe_load(action.read_text("utf-8"))["runs"]["steps"])
    for step in steps:
        if "run" in step:
            assert step.get("shell") == "bash", step.get("name")


@pytest.mark.parametrize("caller", CALLERS, ids=_ids(CALLERS))
def test_a_caller_uses_this_repository_at_its_major_version_and_only_what_exists(caller: Path) -> None:
    for path, ref in OWN.findall(caller.read_text("utf-8")):
        assert ref == MAJOR
        assert (ROOT / path).exists(), path


def test_the_reusable_workflows_are_called_by_their_callers() -> None:
    called = {path for caller in CALLERS for path, _ in OWN.findall(caller.read_text("utf-8"))}
    reusable = {
        workflow.relative_to(ROOT).as_posix()
        for workflow in (ROOT / ".github/workflows").glob("*.yml")
        if "workflow_call" in workflow.read_text("utf-8") and workflow.name not in OWN_WORKFLOWS | SUPERSEDED
    }
    assert reusable <= called
    assert {action.parent.relative_to(ROOT).as_posix() for action in ACTIONS} <= called


@pytest.mark.parametrize("kind", KINDS)
def test_the_shared_conventions_name_the_major_version_the_callers_use(kind: str) -> None:
    assert f"at `@{MAJOR}`" in (ROOT / kind / "template/CLAUDE.md").read_text("utf-8")


def _job_names(job: dict[str, Any]) -> set[str]:
    """The names a job's checks get, one per combination of its matrix."""
    name = str(job.get("name"))
    matrix = cast(dict[str, Any], job.get("strategy", {}).get("matrix", {}))
    names = {name}
    for key, values in matrix.items():
        names = {
            each.replace(f"${{{{ matrix.{key} }}}}", str(value))
            for each in names
            for value in cast(list[Any], values)
        }
    return names


@pytest.mark.parametrize("kind", KINDS)
def test_the_checks_a_ruleset_requires_keep_their_names(kind: str) -> None:
    """The ruleset requires checks by name; a job called through a reusable workflow gets a
    prefixed name, so a required check is a job of the caller itself."""
    ruleset = json.loads((ROOT / kind / "template/.github/rulesets/main.json").read_text("utf-8"))
    rule = next(rule for rule in ruleset["rules"] if rule["type"] == "required_status_checks")
    required = {check["context"] for check in rule["parameters"]["required_status_checks"]}
    callers = [
        path
        for template in (ROOT / "common/template", ROOT / kind / "template")
        for path in (template / ".github/workflows").glob("*.yml")
    ]
    names = {
        name
        for caller in callers
        for job in cast(dict[str, dict[str, Any]], yaml.safe_load(caller.read_text("utf-8"))["jobs"]).values()
        if "uses" not in job
        for name in _job_names(job)
    }
    assert required <= names


def test_a_library_is_tested_on_every_python_it_supports() -> None:
    tests = yaml.safe_load((ROOT / "python/template/.github/workflows/tests.yml").read_text("utf-8"))
    release = yaml.safe_load((ROOT / ".github/workflows/python-release.yml").read_text("utf-8"))
    for workflow in (tests, release):
        assert tuple(workflow["jobs"]["test"]["strategy"]["matrix"]["python-version"]) == PYTHON_VERSIONS


@pytest.mark.skipif(shutil.which("jq") is None, reason="jq is not installed")
class TestBranchTestBuilds:
    RELEASES: list[dict[str, Any]] = [
        {"tag_name": "v0.2.9b1", "prerelease": True, "body": "notes\r\ntest-build-branch: fix/a\r\n"},
        {"tag_name": "v0.2.9b2", "prerelease": True, "body": "test-build-branch: fix/ab"},
        {"tag_name": "v0.2.9b3", "prerelease": True, "body": "test-build-branch: fix/a-2\n"},
        {"tag_name": "v0.2.9b4", "prerelease": True, "body": "x test-build-branch: fix/a"},
        {"tag_name": "v0.2.9", "prerelease": False, "body": "test-build-branch: fix/a"},
        {"tag_name": "v0.2.9b5", "prerelease": True, "body": None},
        {"tag_name": "v0.2.9b6", "prerelease": True, "body": "built\n\ntest-build-branch: fix/a"},
    ]

    def _select(self, branch: str, tag: str | None = None) -> list[str]:
        env = {key: value for key, value in os.environ.items() if key != "TAG"}
        env["BRANCH"] = branch
        if tag is not None:
            env["TAG"] = tag
        result = subprocess.run(
            ["jq", "-r", "-f", str(BRANCH_TEST_BUILDS)],
            input=json.dumps(self.RELEASES),
            capture_output=True,
            text=True,
            check=True,
            env=env,
        )
        return result.stdout.split()

    def test_only_the_branchs_own_test_builds_are_selected(self) -> None:
        assert self._select("fix/a") == ["v0.2.9b1", "v0.2.9b6"]

    def test_the_test_build_being_published_is_not_selected(self) -> None:
        assert self._select("fix/a", tag="v0.2.9b6") == ["v0.2.9b1"]

    def test_a_branch_whose_name_starts_another_does_not_select_it(self) -> None:
        assert self._select("fix/ab") == ["v0.2.9b2"]
        assert self._select("fix/") == []


@pytest.mark.skipif(shutil.which("shellcheck") is None, reason="shellcheck is not installed")
@pytest.mark.parametrize("action", ACTIONS, ids=_ids(ACTIONS))
def test_every_script_of_an_action_passes_shellcheck(action: Path, tmp_path: Path) -> None:
    """actionlint checks the scripts of workflows, not those of actions."""
    steps = cast(list[dict[str, Any]], yaml.safe_load(action.read_text("utf-8"))["runs"]["steps"])
    for number, step in enumerate(steps):
        if "run" not in step:
            continue
        assert "${{" not in step["run"], "values reach a script through env, never expanded into it"
        script = tmp_path / f"step{number}.sh"
        script.write_text(f"#!/bin/bash\nset -eo pipefail\n{step['run']}", "utf-8")
        result = subprocess.run(["shellcheck", str(script)], capture_output=True, text=True)
        assert result.returncode == 0, result.stdout


@pytest.mark.skipif(shutil.which("shellcheck") is None, reason="shellcheck is not installed")
def test_the_integrations_install_script_passes_shellcheck() -> None:
    result = subprocess.run(["shellcheck", str(HA_INSTALL)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout


@pytest.mark.parametrize("script", [HA_INSTALL, ROOT / "python/actions/tests/action.yml"])
def test_the_tests_install_a_libraries_branch_in_place_of_its_pin(script: Path) -> None:
    """Installing the pins first fails where the branch needs what only a library's branch has."""
    text = script.read_text()
    assert '"$common/libraries.py" requirements "$requirements"' in text
    assert "-r requirements-test.txt" not in text
    assert text.index('libraries.py" requirements') < text.index('-r "$requirements"')


def test_the_integrations_tests_run_on_the_oldest_home_assistant_supported_too() -> None:
    """Every check that runs on the newest Home Assistant runs on the oldest, with its packages."""
    steps = cast(list[dict[str, Any]], yaml.safe_load(HA_TESTS.read_text("utf-8"))["runs"]["steps"])
    oldest = [step for step in steps if step.get("if") == "steps.minimum.outputs.version != ''"]
    runs = "\n".join(str(step["run"]) for step in oldest)
    assert '"homeassistant==$HOME_ASSISTANT" pytest-homeassistant-custom-component' in runs
    assert "minimum-requirements" in runs
    assert '"$RUNNER_TEMP/minimum/bin/pyright" --pythonpath "$RUNNER_TEMP/minimum/bin/python"' in runs
    assert '"$RUNNER_TEMP/minimum/bin/python" -m pytest' in runs
    assert "contract.py\" minimum-check" in runs
    assert all("install.sh" in str(step["run"]) for step in steps if str(step.get("name", "")).startswith("Install"))


def test_each_home_assistant_is_tested_on_the_python_it_requires() -> None:
    steps = cast(list[dict[str, Any]], yaml.safe_load(HA_TESTS.read_text("utf-8"))["runs"]["steps"])
    pythons = [step for step in steps if str(step.get("uses", "")).startswith("actions/setup-python@")]
    assert [step["with"]["python-version"] for step in pythons] == [
        "${{ steps.python.outputs.minimum }}",
        "${{ steps.python.outputs.newest }}",
    ]
    venv = next(step for step in steps if "-m venv" in str(step.get("run", "")))
    assert venv["env"]["PYTHON"] == "${{ steps.minimum-python.outputs.python-path }}"
    assert '"$PYTHON" -m venv' in venv["run"]


def test_only_dependabots_pull_requests_are_handled() -> None:
    caller = yaml.safe_load((ROOT / "common/template/.github/workflows/dependabot-merge.yml").read_text("utf-8"))
    assert caller["jobs"]["merge"]["if"] == "github.event.pull_request.user.login == 'dependabot[bot]'"
    assert caller["jobs"]["merge"]["permissions"] == {
        "actions": "write", "contents": "write", "issues": "write", "pull-requests": "write"
    }


def _merge_steps() -> dict[str, dict[str, Any]]:
    return {str(step["name"]): step for step in _steps(_workflow("dependabot-merge.yml")["jobs"]["merge"])}


def test_an_update_is_merged_at_the_commit_tested_and_the_draft_follows() -> None:
    steps = _merge_steps()
    merge = steps["Wait for every check, then merge"]
    assert merge["if"] == "steps.decide.outputs.action == 'merge'"
    assert '--match-head-commit "$HEAD"' in merge["run"]
    assert merge["env"]["HEAD"] == "${{ github.event.pull_request.head.sha }}"
    assert steps["Update the release draft"]["if"].startswith("steps.merge.outputs.merged == 'true'")
    assert "gh workflow run release-drafter.yml" in steps["Update the release draft"]["run"]


def test_the_owner_is_assigned_only_an_update_that_needs_them() -> None:
    steps = _merge_steps()
    assert steps["Leave a new major version to the owner"]["if"] == "steps.decide.outputs.action == 'owner'"
    assert '--add-assignee "$OWNER"' in steps["Leave a new major version to the owner"]["run"]
    merge = steps["Wait for every check, then merge"]["run"]
    assert merge.index('--add-assignee "$OWNER"') < merge.index("exit 1")
    assert '--add-assignee' not in steps["Close an update made for a Home Assistant pre-release"]["run"]


def test_no_template_assigns_dependabots_updates_or_proposes_actions() -> None:
    for kind in KINDS:
        config = yaml.safe_load((ROOT / kind / "template/.github/dependabot.yml").read_text("utf-8"))
        for update in config["updates"]:
            assert "assignees" not in update
            assert update["package-ecosystem"] != "github-actions"
            assert update["cooldown"] == {"default-days": 3}
            assert all(group["update-types"] == ["minor", "patch"] for group in update["groups"].values())


def test_the_owner_hears_of_an_update_only_once() -> None:
    steps = _merge_steps()
    for script in (steps["Leave a new major version to the owner"]["run"], steps["Wait for every check, then merge"]["run"]):
        assert script.index("grep -qx \"$OWNER\"") < script.index("gh pr comment")


def test_this_repository_merges_every_dependabot_update_its_checks_pass() -> None:
    caller = _workflow("merge-dependabot.yml")["jobs"]["merge"]
    assert caller["if"] == "github.event.pull_request.user.login == 'dependabot[bot]'"
    assert caller["uses"] == "./.github/workflows/dependabot-merge.yml"
    assert caller["with"] == {"release-drafter": False}
    config = yaml.safe_load((ROOT / ".github/dependabot.yml").read_text("utf-8"))
    for update in config["updates"]:
        assert "assignees" not in update
        assert update["cooldown"] == {"default-days": 3}
        assert all(group["update-types"] == ["minor", "patch"] for group in update["groups"].values())


CANARIES = {
    "canary-integration": ("HairingX/ha_duka_connect", "ha"),
    "canary-library": ("HairingX/event_connect", "python"),
    "canary-card": ("HairingX/ha_aula_connect_card", "card"),
}


def _canary_steps(job: str) -> dict[str, dict[str, Any]]:
    return {str(step.get("id", step["name"])): step for step in _steps(_workflow("ci.yml")["jobs"][job])}


@pytest.mark.parametrize("job", CANARIES)
def test_the_canary_runs_a_repositorys_main_with_this_commits_tests_and_the_published_ones(job: str) -> None:
    repository, kind = CANARIES[job]
    steps = list(_canary_steps(job).values())
    assert steps[0]["with"]["repository"] == repository
    assert steps[0]["with"]["ref"] == "main"
    assert steps[1]["with"] == {"ref": "${{ inputs.ref }}", "path": ".workflows", "persist-credentials": False}
    by_id = _canary_steps(job)
    assert by_id["change"]["uses"] == f"./.workflows/{kind}/actions/tests"
    assert by_id["published"]["uses"] == f"HairingX/workflows/{kind}/actions/tests@{MAJOR}"
    assert by_id["change"]["with"] == by_id["published"]["with"]
    assert by_id["change"]["with"]["template-check"] == "false"
    if kind == "card":
        assert steps[0]["with"]["path"] == by_id["change"]["with"]["path"] == "card"
    assert by_id["change"]["continue-on-error"] is by_id["published"]["continue-on-error"] is True
    assert by_id["published"]["if"] == "steps.change.outcome == 'failure'"


@pytest.mark.parametrize(
    ("change", "published", "fails", "says"),
    [
        ("success", "skipped", False, "passes with this commit's actions"),
        ("failure", "success", True, "::error::"),
        ("failure", "failure", False, "::warning::"),
    ],
)
def test_the_canary_fails_only_a_change_that_breaks_a_repository_the_published_tests_pass(
    change: str, published: str, fails: bool, says: str
) -> None:
    verdict = [step for step in _steps(_workflow("ci.yml")["jobs"]["canary-card"]) if "run" in step][-1]
    env = {**verdict["env"], "CHANGE": change, "PUBLISHED": published}
    result = subprocess.run(["bash", "-c", verdict["run"]], env=env, capture_output=True, text=True, check=False)
    assert (result.returncode != 0) is fails
    assert says in result.stdout


def test_the_canary_runs_on_pull_requests_and_publish_but_a_new_major_version() -> None:
    ci = cast(dict[Any, Any], _workflow("ci.yml"))
    assert ci[True]["workflow_call"]["inputs"]["new-major"]["default"] is False
    for job in CANARIES:
        assert ci["jobs"][job]["if"] == "github.event_name != 'push' && !inputs.new-major"
    publish = _workflow("publish.yml")
    assert publish["jobs"]["check"]["with"]["new-major"] == "${{ needs.prepare.outputs.new-major == 'true' }}"
    assert 'grep -qx "v${VERSION%%.*}" "$RUNNER_TEMP/tags"' in _steps(publish["jobs"]["prepare"])[-1]["run"]


def test_release_drafter_is_started_after_a_merge_only_where_there_is_one() -> None:
    reusable = cast(dict[Any, Any], _workflow("dependabot-merge.yml"))
    assert reusable[True]["workflow_call"]["inputs"]["release-drafter"]["default"] is True
    assert "inputs.release-drafter" in _merge_steps()["Update the release draft"]["if"]


def test_a_card_is_built_and_tested_on_the_newest_node_lts() -> None:
    for path in (ROOT / "card/actions/tests/action.yml", ROOT / ".github/workflows/card-release.yml", ROOT / ".github/workflows/card-test-build.yml"):
        text = path.read_text("utf-8")
        assert "node-version: lts/*" in text
        assert '"22"' not in text


def test_the_test_harness_is_proposed_on_its_own() -> None:
    config = yaml.safe_load((ROOT / "ha/template/.github/dependabot.yml").read_text("utf-8"))
    pip = next(update for update in config["updates"] if update["package-ecosystem"] == "pip")
    assert pip["groups"]["test-tools"]["exclude-patterns"] == ["pytest-homeassistant-custom-component"]


def test_release_drafter_updates_the_draft_when_started_by_hand() -> None:
    caller = yaml.safe_load((ROOT / "common/template/.github/workflows/release-drafter.yml").read_text("utf-8"))
    assert "workflow_dispatch" in caller[True]
    job = _workflow("release-drafter.yml")["jobs"]["update_release_draft"]
    assert "github.event_name == 'workflow_dispatch'" in job["if"]


@pytest.mark.parametrize("workflow", ["ha-release.yml", "python-release.yml", "card-release.yml"])
def test_a_release_accepts_a_draft_release_drafter_was_started_for_by_hand(workflow: str) -> None:
    script = (ROOT / ".github/workflows" / workflow).read_text("utf-8")
    assert 'select(.event == "push" or .event == "workflow_dispatch")' in script
    assert "--event push" not in script


def _workflow(name: str) -> dict[str, Any]:
    return cast(dict[str, Any], yaml.safe_load((ROOT / ".github/workflows" / name).read_text("utf-8")))


def _steps(job: dict[str, Any]) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], job["steps"])


def test_the_shared_test_build_cleanup_does_what_the_integrations_does() -> None:
    """The integrations call their own until the next major; the two must not drift apart."""
    assert _workflow("test-build-cleanup.yml")["jobs"] == _workflow("ha-test-build-cleanup.yml")["jobs"]


@pytest.mark.parametrize("workflow", ["card-release.yml", "card-test-build.yml"])
def test_a_cards_packages_never_run_where_a_token_can_push(workflow: str) -> None:
    """npm runs the install scripts of every package it installs."""
    for name, job in cast(dict[str, dict[str, Any]], _workflow(workflow)["jobs"]).items():
        runs = "\n".join(str(step.get("run", "")) for step in _steps(job))
        uses = [str(step.get("uses", "")) for step in _steps(job)]
        if "npm" in runs or any("card/actions/tests" in use for use in uses):
            assert job["permissions"] == {"contents": "read"}, name
            for step in _steps(job):
                if str(step.get("uses", "")).startswith("actions/checkout@"):
                    assert step["with"]["persist-credentials"] is False, name


@pytest.mark.parametrize("workflow", ["card-release.yml", "card-test-build.yml"])
def test_a_card_publishes_the_bundle_built_with_its_version_after_every_check(workflow: str) -> None:
    jobs = cast(dict[str, dict[str, Any]], _workflow(workflow)["jobs"])
    assert set(jobs["publish"]["needs"]) == {"prepare", "test", "hacs", "build"}
    build = "\n".join(str(step.get("run", "")) for step in _steps(jobs["build"]))
    assert 'CARD_VERSION="$VERSION" npm run build' in build
    assert 'bundle.py" check . "$VERSION"' in build
    assert jobs["build"]["env"]["VERSION"] == "${{ needs.prepare.outputs.version }}"
    published = "\n".join(str(step.get("run", "")) for step in _steps(jobs["publish"]))
    assert 'gh release create "$TAG" "$BUNDLE"' in published
    assert 'gh release upload "$TAG" "$BUNDLE"' in published


@pytest.mark.parametrize("workflow", ["card-release.yml", "card-test-build.yml"])
def test_a_cards_lint_never_sees_the_tools_checked_out_beside_it(workflow: str) -> None:
    """A card's lint checks every file under its directory, and the tools are not the card's."""
    for name, job in cast(dict[str, dict[str, Any]], _workflow(workflow)["jobs"]).items():
        tests = [step for step in _steps(job) if "card/actions/tests" in str(step.get("uses", ""))]
        if not tests:
            continue
        checkouts = [step["with"] for step in _steps(job) if str(step.get("uses", "")).startswith("actions/checkout@")]
        card = [checkout.get("path", ".") for checkout in checkouts if "repository" not in checkout]
        tools = [checkout["path"] for checkout in checkouts if "repository" in checkout]
        assert card == [tests[0]["with"]["path"]], name
        assert all(not tool.startswith(f"{card[0]}/") and card[0] != "." for tool in tools), name


def test_the_cards_tests_run_where_the_card_is_checked_out() -> None:
    action = yaml.safe_load((ROOT / "card/actions/tests/action.yml").read_text("utf-8"))
    for step in action["runs"]["steps"]:
        if "run" in step:
            assert step["working-directory"] == "${{ inputs.path }}", step["name"]
    node = next(step for step in action["runs"]["steps"] if str(step.get("uses", "")).startswith("actions/setup-node@"))
    assert node["with"]["cache-dependency-path"] == "${{ inputs.path }}/package-lock.json"


def test_the_cards_tests_hold_it_to_full_coverage_whatever_its_configuration() -> None:
    script = (ROOT / "card/actions/tests/action.yml").read_text("utf-8")
    assert "npm test -- --coverage.enabled=true --coverage.thresholds.100=true" in script
    for step in ("npm ci", "npm run lint", "npm run typecheck", "npm run build", "card_contract.py", "check card ."):
        assert step in script


def test_hacs_validates_a_card_only_once_a_final_release_carries_it() -> None:
    """HACS finds a card among the newest final release's assets; before one, validation fails."""
    action = yaml.safe_load((ROOT / "card/actions/hacs/action.yml").read_text("utf-8"))
    steps = cast(list[dict[str, Any]], action["runs"]["steps"])
    assert "releases/latest" in steps[0]["run"]
    validations = [step for step in steps if str(step.get("uses", "")).startswith("hacs/action@")]
    assert len(validations) == 2
    for step in validations:
        assert step["with"] == {"category": "plugin"}
        assert "steps.released.outputs.found == 'true'" in step["if"]
    # An empty REPOSITORY_REF names no ref, so it is set only when a commit is given.
    assert [step.get("env") for step in validations] == [None, {"REPOSITORY_REF": "${{ inputs.ref }}"}]
