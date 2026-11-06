"""What every integration's repository promises, checked against the installed environment.

    contract.py ROOT        checks the repository at ROOT, with the tests' packages installed,
                            and fails with one error per broken promise
    contract.py pins ROOT   prints, one per line, Home Assistant's pin of each package the
                            manifest's requirements install that its own integrations pin
    contract.py minimum ROOT
                            prints the oldest Home Assistant hacs.json supports, where it is
                            older than the one installed, and nothing otherwise
    contract.py minimum-requirements ROOT
                            prints requirements-test.txt as the Home Assistant installed runs it
    contract.py minimum-check ROOT
                            checks, with the oldest Home Assistant supported installed, that it
                            is hacs.json's and accepts the manifest's requirements

The promises: the manifest says 0.0.0, as the version lives in the release's tag and zip; HACS
installs a zip named after the domain and requires a Home Assistant no newer than the one the
tests run, and the tests run that one too; every requirement is one Home Assistant accepts, by
hassfest's rules for a custom integration, pinned with == where those rules allow, run by the
tests and pinned in requirements-test.txt; the quality scale states every rule; and every
translation holds the same keys.
"""

import importlib.metadata
import importlib.util
import json
import sys
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import yaml
from packaging.requirements import InvalidRequirement, Requirement
from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

# The tools every kind of repository shares live beside this kind's own.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "common" / "tools"))

from repository import domain, integration  # noqa: E402
from settings import check_standard, coverage, tool, transition  # noqa: E402

HARNESSES = ("pytest-homeassistant", "pytest-homeassistant-custom-component")
"""The test harnesses, each released for one Home Assistant version: Home Assistant's own, and
the one it replaced, accepted until every integration has moved."""

QUALITY_SCALE_RULES = frozenset({
    # Bronze
    "action-setup", "appropriate-polling", "brands", "common-modules",
    "config-flow-test-coverage", "config-flow", "dependency-transparency", "docs-actions",
    "docs-conditions", "docs-high-level-description", "docs-installation-instructions",
    "docs-removal-instructions", "docs-triggers", "entity-event-setup", "entity-unique-id",
    "has-entity-name", "runtime-data", "test-before-configure", "test-before-setup",
    "unique-config-entry",
    # Silver
    "action-exceptions", "config-entry-unloading", "docs-configuration-parameters",
    "docs-installation-parameters", "entity-unavailable", "integration-owner",
    "log-when-unavailable", "parallel-updates", "reauthentication-flow", "test-coverage",
    # Gold
    "devices", "diagnostics", "discovery-update-info", "discovery", "docs-data-update",
    "docs-examples", "docs-known-limitations", "docs-supported-devices",
    "docs-supported-functions", "docs-troubleshooting", "docs-use-cases", "dynamic-devices",
    "entity-category", "entity-device-class", "entity-disabled-by-default",
    "entity-translations", "exception-translations", "icon-translations",
    "reconfiguration-flow", "repair-issues", "stale-devices",
    # Platinum
    "async-dependency", "inject-websession", "strict-typing",
})
"""The rules of Home Assistant's Integration Quality Scale, as hassfest's ALL_RULES lists them.
hassfest does not check this file for a custom integration, so this does."""


def _json(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text("utf-8")))


def installed_version(name: str) -> str | None:
    """The version of `name` installed, marked as a local build when it came from a URL.

    A library taken from a branch is installed from GitHub's source download (PEP 610 records
    it in direct_url.json): its version, worked out without the tags, can look like a release.
    """
    try:
        distribution = importlib.metadata.distribution(name)
    except importlib.metadata.PackageNotFoundError:
        return None
    if distribution.read_text("direct_url.json") is not None:
        return f"{distribution.version}+url"
    return distribution.version


def _installed(name: str) -> str | None:
    return installed_version(name)


def installed_harness() -> str | None:
    """The version of the test harness installed, None if none is."""
    return next((version for name in HARNESSES if (version := _installed(name)) is not None), None)


def released(version: str) -> bool:
    """Whether `version` is a release, not a build of a branch."""
    try:
        parsed = Version(version)
    except InvalidVersion:
        return False
    return parsed.local is None and parsed.dev is None


def check_manifest(manifest: Mapping[str, Any]) -> Iterator[str]:
    """The manifest says 0.0.0: releases set the version in their zip only."""
    if manifest.get("version") != "0.0.0":
        yield f"manifest.json says version {manifest.get('version')!r}; it must say '0.0.0'"


def _version(text: object) -> Version | None:
    if not isinstance(text, str):
        return None
    try:
        return Version(text)
    except InvalidVersion:
        return None


def check_hacs(hacs: Mapping[str, Any], name: str, home_assistant: str | None) -> Iterator[str]:
    """HACS installs the release's zip, named after the domain, on a Home Assistant no newer than
    `home_assistant`, the one tested."""
    if hacs.get("zip_release") is not True:
        yield "hacs.json must set zip_release to true"
    if hacs.get("filename") != f"{name}.zip":
        yield f"hacs.json names the zip {hacs.get('filename')!r}; it must be '{name}.zip'"
    required = _version(hacs.get("homeassistant"))
    tested = _version(home_assistant)
    if required is None:
        yield (
            "hacs.json must give the oldest Home Assistant the integration supports in "
            f"homeassistant, such as {home_assistant!r}"
        )
    elif tested is None or required > tested:
        yield (
            f"hacs.json requires Home Assistant {hacs['homeassistant']!r}, "
            f"newer than the {home_assistant!r} the tests run"
        )


def minimum(hacs: Mapping[str, Any], home_assistant: str | None) -> str | None:
    """The oldest Home Assistant hacs.json supports, where it is older than `home_assistant`."""
    required = _version(hacs.get("homeassistant"))
    tested = _version(home_assistant)
    if required is None or tested is None or required >= tested:
        return None
    return cast(str, hacs["homeassistant"])


@dataclass(frozen=True)
class HomeAssistant:
    """What the installed Home Assistant requires of a custom integration's requirements."""

    dependencies: frozenset[str] = frozenset()
    """Packages Home Assistant itself installs, by canonical name."""
    pins: Mapping[str, frozenset[str]] = field(default_factory=dict[str, frozenset[str]])
    """The versions Home Assistant's own integrations pin, by canonical name."""
    constraints: Mapping[str, SpecifierSet] = field(default_factory=dict[str, SpecifierSet])
    """Home Assistant's package constraints, by canonical name."""


def _requirements(lines: list[str]) -> Iterator[Requirement]:
    for line in lines:
        text = line.split("#", 1)[0].strip()
        if not text or text.startswith("-"):
            continue
        try:
            yield Requirement(text)
        except InvalidRequirement:
            continue


def home_assistant(package: Path, dependencies: list[str]) -> HomeAssistant:
    """What the Home Assistant installed at `package`, which requires `dependencies`, requires."""
    pins: dict[str, set[str]] = {}
    for manifest in sorted((package / "components").glob("*/manifest.json")):
        for requirement in _requirements(cast(list[str], _json(manifest).get("requirements", []))):
            for specifier in requirement.specifier:
                if specifier.operator == "==":
                    pins.setdefault(canonicalize_name(requirement.name), set()).add(specifier.version)
    constraints_file = package / "package_constraints.txt"
    constraints: dict[str, SpecifierSet] = {
        canonicalize_name(requirement.name): requirement.specifier
        for requirement in _requirements(
            constraints_file.read_text("utf-8").splitlines() if constraints_file.exists() else []
        )
    }
    return HomeAssistant(
        dependencies=frozenset(
            canonicalize_name(requirement.name)
            for requirement in _requirements(dependencies)
            if requirement.marker is None
        ),
        pins={name: frozenset(versions) for name, versions in pins.items()},
        constraints=constraints,
    )


def _installed_home_assistant() -> HomeAssistant:
    spec = importlib.util.find_spec("homeassistant")
    if spec is None or spec.origin is None:
        return HomeAssistant()
    return home_assistant(Path(spec.origin).parent, importlib.metadata.requires("homeassistant") or [])


def requirement_closure(
    requirements: list[str], requires: Callable[[str], list[str] | None]
) -> set[str]:
    """The canonical names of `requirements` and of everything they require, as `requires` reads
    each package's own requirements; extras and markers that do not apply are left out."""
    found: set[str] = set()
    pending = list(_requirements(requirements))
    while pending:
        requirement = pending.pop()
        if requirement.marker is not None and not requirement.marker.evaluate({"extra": ""}):
            continue
        name = canonicalize_name(requirement.name)
        if name in found:
            continue
        found.add(name)
        pending += _requirements(requires(name) or [])
    return found


def _requires(name: str) -> list[str] | None:
    try:
        return importlib.metadata.requires(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def home_assistant_pins(
    requirements: list[str], core: HomeAssistant, requires: Callable[[str], list[str] | None]
) -> list[str]:
    """Home Assistant's pin of each package `requirements` install that its own integrations pin.

    Such a package is installed at Home Assistant's version, as Home Assistant installs it, so the
    tests run what a user's Home Assistant may run; one Home Assistant itself requires is left to
    it.
    """
    return [
        f"{name}=={max(core.pins[name], key=Version)}"
        for name in sorted(requirement_closure(requirements, requires))
        if name in core.pins and name not in core.dependencies
    ]


def check_requirements(
    requirements: list[str],
    pinned: list[str],
    installed: Mapping[str, str | None],
    core: HomeAssistant,
) -> Iterator[str]:
    """Every requirement is one Home Assistant accepts, the tests run it, and they pin it.

    The rules are hassfest's for a custom integration, which shares Home Assistant's Python
    environment: a package Home Assistant itself installs is not listed; one its own integrations
    pin is required at a minimum version that admits theirs, so that it follows Home Assistant's
    updates, and the tests run Home Assistant's version; one its package constraints bound must
    admit their bound. Any other is pinned with ==, and the tests run that version. A library
    installed from a branch is no release, so its version is not checked.
    """
    test_pins = {canonicalize_name(r.name): r for r in _requirements(pinned) if not r.url}
    for text in requirements:
        refusal = refused(text, core)
        if refusal is not None:
            yield refusal
            continue
        requirement = Requirement(text)
        name = canonicalize_name(requirement.name)
        exact = [s.version for s in requirement.specifier if s.operator in ("==", "===")]
        version = installed.get(name)
        tested = test_pins.get(name)
        tested_versions: set[str] = (
            {s.version for s in tested.specifier if s.operator == "=="} if tested else set()
        )
        theirs = core.pins.get(name)
        if theirs:
            if not tested_versions & theirs:
                yield f"requirements-test.txt must pin {requirement.name} to the version Home Assistant's own integrations pin ({', '.join(sorted(theirs))})"
            elif version is not None and version not in theirs:
                yield f"the tests run {requirement.name} {version}, not the version Home Assistant's own integrations pin"
            continue
        if version is None:
            yield f"{requirement.name} is required by the manifest but not installed"
            continue
        if not released(version):
            continue
        if version != exact[0]:
            yield f"the manifest pins {text!r}, but the tests run {requirement.name} {version}"
        if tested_versions != {exact[0]}:
            yield f"requirements-test.txt must pin {text!r}, as the manifest does"


def refused(text: str, core: HomeAssistant) -> str | None:
    """Why `core` refuses the manifest's requirement `text`, by hassfest's rules, if it does."""
    requirement = Requirement(text)
    name = canonicalize_name(requirement.name)
    exact = [s.version for s in requirement.specifier if s.operator in ("==", "===")]
    if name in core.dependencies:
        return f"{requirement.name} is a dependency of Home Assistant itself; the manifest must not list it"
    theirs = core.pins.get(name)
    if theirs:
        if exact:
            return (
                f"the manifest pins {text!r}, a package Home Assistant's own integrations use "
                f"({', '.join(sorted(theirs))}); require a minimum version instead, such as "
                f"'{requirement.name}>={min(theirs, key=Version)}'"
            )
        if not all(requirement.specifier.contains(v, prereleases=True) for v in theirs):
            return f"the manifest's {text!r} excludes {requirement.name} {', '.join(sorted(theirs))}, which Home Assistant's own integrations pin"
        return None
    if len(exact) != 1 or len(requirement.specifier) != 1:
        return f"the manifest's requirement {text!r} must pin one version with =="
    constraint = core.constraints.get(name)
    if constraint is not None and not constraint.contains(exact[0], prereleases=True):
        return f"the manifest pins {text!r}, which Home Assistant's package constraints ({requirement.name}{constraint}) exclude"
    return None


def minimum_test_pins(pinned: list[str], core: HomeAssistant, harness: str | None) -> list[str]:
    """The lines of requirements-test.txt as an older Home Assistant runs them.

    `harness` is the version of the test harness installed for that Home Assistant. A package
    Home Assistant itself installs is left to it, and one its own integrations pin is at their
    version, as Home Assistant installs it.
    """
    lines: list[str] = []
    for line in pinned:
        text = line.split("#", 1)[0].strip()
        if not text:
            continue
        try:
            requirement = Requirement(text)
        except InvalidRequirement:
            lines.append(text)
            continue
        name = canonicalize_name(requirement.name)
        if requirement.url:
            lines.append(text)
        elif name in HARNESSES and harness is not None:
            lines.append(f"{requirement.name}=={harness}")
        elif name in core.dependencies:
            continue
        elif name in core.pins:
            lines.append(f"{requirement.name}=={max(core.pins[name], key=Version)}")
        else:
            lines.append(text)
    return lines


def check_minimum(
    hacs: Mapping[str, Any], home_assistant: str | None, requirements: list[str], core: HomeAssistant
) -> Iterator[str]:
    """`home_assistant`, the one tested, is the oldest hacs.json supports, and `core`, what it
    requires, accepts every requirement of the manifest."""
    if hacs.get("homeassistant") != home_assistant:
        yield (
            f"hacs.json requires Home Assistant {hacs.get('homeassistant')!r}, "
            f"but the tests of the oldest supported run {home_assistant!r}"
        )
    for text in requirements:
        refusal = refused(text, core)
        if refusal is not None:
            yield refusal


def check_test_pins(requirements: list[str], pinned: list[str], core: HomeAssistant) -> Iterator[str]:
    """The tests run Home Assistant's version of every other package it pins or bounds.

    A library's own requirements share Home Assistant's environment as the manifest's do, so the
    tests run the version Home Assistant's own integrations pin, and one its constraints admit.
    """
    required = {canonicalize_name(Requirement(text).name) for text in requirements}
    for requirement in _requirements(pinned):
        name = canonicalize_name(requirement.name)
        exact = [s.version for s in requirement.specifier if s.operator == "=="]
        if requirement.url or name in required or len(exact) != 1:
            continue
        theirs = core.pins.get(name)
        if theirs and exact[0] not in theirs:
            yield (
                f"requirements-test.txt pins {requirement.name} {exact[0]}, but Home Assistant's own "
                f"integrations pin {', '.join(sorted(theirs))}, the version the tests must run"
            )
            continue
        constraint = core.constraints.get(name)
        if constraint is not None and not constraint.contains(exact[0], prereleases=True):
            yield (
                f"requirements-test.txt pins {requirement.name} {exact[0]}, which Home Assistant's "
                f"package constraints ({requirement.name}{constraint}) exclude"
            )


def check_quality_scale(rules: Mapping[str, Any]) -> Iterator[str]:
    """The quality scale states every rule, and a reason for each one not done."""
    for rule in sorted(QUALITY_SCALE_RULES - set(rules)):
        yield f"quality_scale.yaml does not state the rule {rule}"
    for rule in sorted(set(rules) - QUALITY_SCALE_RULES):
        yield f"quality_scale.yaml states {rule}, which is no rule of the quality scale"
    for rule, state in sorted(rules.items()):
        if state == "done":
            continue
        if not isinstance(state, dict):
            yield f"quality_scale.yaml: {rule} must be done, or have a status and a comment"
            continue
        entry = cast(dict[str, Any], state)
        if entry.get("status") not in ("done", "exempt", "todo"):
            yield f"quality_scale.yaml: {rule} has status {entry.get('status')!r}"
        elif entry["status"] != "done" and not entry.get("comment"):
            yield f"quality_scale.yaml: {rule} is {entry['status']} without a comment saying why"


def keys(tree: Mapping[str, Any], prefix: str = "") -> set[str]:
    """Every key of the nested `tree`, as a dotted path."""
    found: set[str] = set()
    for key, value in tree.items():
        path = f"{prefix}{key}"
        found.add(path)
        if isinstance(value, Mapping):
            found |= keys(cast(Mapping[str, Any], value), f"{path}.")
    return found


def check_translations(translations: Mapping[str, Mapping[str, Any]]) -> Iterator[str]:
    """English is there, and every translation holds the same keys as English."""
    if "en" not in translations:
        yield "translations/en.json is missing"
        return
    english = keys(translations["en"])
    for language, tree in sorted(translations.items()):
        if language == "en":
            continue
        other = keys(tree)
        for key in sorted(english - other):
            yield f"translations/{language}.json lacks {key}"
        for key in sorted(other - english):
            yield f"translations/{language}.json has {key}, which English does not"


def check(root: Path) -> list[str]:
    """Every broken promise of the repository at `root`."""
    directory = integration(root)
    name = domain(root)
    manifest = _json(directory / "manifest.json")
    requirements = cast(list[str], manifest.get("requirements", []))
    pinned = (root / "requirements-test.txt").read_text("utf-8").splitlines()
    installed: dict[str, str | None] = {
        canonicalize_name(Requirement(r).name): _installed(Requirement(r).name) for r in requirements
    }
    quality_scale = directory / "quality_scale.yaml"
    rules: dict[str, Any] = {}
    errors: list[str] = []
    if quality_scale.exists():
        rules = cast(dict[str, Any], yaml.safe_load(quality_scale.read_text("utf-8"))["rules"])
    else:
        errors.append(f"{directory.name}/quality_scale.yaml is missing")
    translations = {
        path.stem: _json(path) for path in sorted((directory / "translations").glob("*.json"))
    }
    core = _installed_home_assistant()
    errors += [
        *check_standard(tool(root, "pyright"), coverage(root), transition(root)),
        *check_manifest(manifest),
        *check_hacs(_json(root / "hacs.json"), name, _installed("homeassistant")),
        *check_requirements(requirements, pinned, installed, core),
        *check_test_pins(requirements, pinned, core),
        *check_quality_scale(rules),
        *check_translations(translations),
    ]
    return errors


def main(arguments: list[str]) -> None:
    """Run the check `arguments` names."""
    match arguments:
        case [root]:
            reason = transition(Path(root))
            if reason is not None:
                print(f"::warning::Not yet held to the whole standard: {reason}")
            errors = check(Path(root))
            for error in errors:
                print(f"::error::{error}")
            if errors:
                sys.exit(1)
            print("Every promise of the repository holds.")
        case ["pins", root]:
            manifest = _json(integration(Path(root)) / "manifest.json")
            requirements = cast(list[str], manifest.get("requirements", []))
            for pin in home_assistant_pins(requirements, _installed_home_assistant(), _requires):
                print(pin)
        case ["minimum", root]:
            version = minimum(_json(Path(root) / "hacs.json"), _installed("homeassistant"))
            if version is not None:
                print(version)
        case ["minimum-requirements", root]:
            pinned = (Path(root) / "requirements-test.txt").read_text("utf-8").splitlines()
            for line in minimum_test_pins(pinned, _installed_home_assistant(), installed_harness()):
                print(line)
        case ["minimum-check", root]:
            manifest = _json(integration(Path(root)) / "manifest.json")
            errors = list(check_minimum(
                _json(Path(root) / "hacs.json"),
                _installed("homeassistant"),
                cast(list[str], manifest.get("requirements", [])),
                _installed_home_assistant(),
            ))
            for error in errors:
                print(f"::error::{error}")
            if errors:
                sys.exit(1)
            print("The oldest Home Assistant supported accepts the integration's requirements.")
        case _:
            sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
