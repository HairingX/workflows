"""What every library's repository promises.

    library_contract.py ROOT    checks the repository at ROOT and fails with one error per
                                broken promise

The promises: the version is worked out from the release's tag when the package is built, never
written in a file; the package ships its types; it supports the Python versions the tests run;
the test tools are pinned with ==, coverage among them; and pyright is strict and the tests cover
every line, unless a transition says why not yet.
"""

import sys
import tomllib
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any, cast

from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name

# The tools every kind of repository shares live beside this kind's own.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "common" / "tools"))

from package import import_name  # noqa: E402
from settings import check_standard, coverage, tool, transition  # noqa: E402

PYTHON_VERSIONS = ("3.14",)
"""The Python versions the tests run on, the oldest first: only the one Home Assistant runs on,
as the libraries are made for its integrations."""
REQUIRES_PYTHON = f">={PYTHON_VERSIONS[0]}"
TEST_TOOLS = ("pyright", "pytest", "pytest-cov")
"""The tools the shared tests run, which requirements-test.txt must pin."""


def check_build(pyproject: Mapping[str, Any]) -> Iterator[str]:
    """The version comes from the tag through setuptools-scm, and the Python versions match."""
    build = cast(dict[str, Any], pyproject.get("build-system", {}))
    requires = [str(item) for item in cast(list[Any], build.get("requires", []))]
    names: set[str] = set()
    for item in requires:
        try:
            names.add(canonicalize_name(Requirement(item).name))
        except InvalidRequirement:
            yield f"[build-system] requires {item!r}, which is no requirement"
    if "setuptools-scm" not in names:
        yield "[build-system] must require setuptools-scm, which works the version out from the tag"
    project = cast(dict[str, Any], pyproject.get("project", {}))
    if "version" in project:
        yield "[project] must not state a version; the release's tag is the version"
    if "version" not in cast(list[Any], project.get("dynamic", [])):
        yield '[project] dynamic must list "version"'
    if project.get("requires-python") != REQUIRES_PYTHON:
        yield f'[project] requires-python must be "{REQUIRES_PYTHON}", the oldest Python the tests run'


def check_test_tools(lines: list[str]) -> Iterator[str]:
    """Every test tool is pinned with ==, and the shared tests' own tools are among them."""
    pinned: set[str] = set()
    for line in lines:
        text = line.split("#", 1)[0].strip()
        if not text or text.startswith("-"):
            continue
        try:
            requirement = Requirement(text)
        except InvalidRequirement:
            yield f"requirements-test.txt: {text!r} is no requirement"
            continue
        specifiers = list(requirement.specifier)
        if len(specifiers) != 1 or specifiers[0].operator != "==":
            yield f"requirements-test.txt must pin {requirement.name} with =="
        pinned.add(canonicalize_name(requirement.name))
    for name in TEST_TOOLS:
        if name not in pinned:
            yield f"requirements-test.txt must pin {name}"


def check(root: Path) -> list[str]:
    """Every broken promise of the repository at `root`."""
    pyproject = tomllib.loads((root / "pyproject.toml").read_text("utf-8"))
    package = import_name(root)
    errors: list[str] = []
    if not (root / "src" / package / "py.typed").is_file():
        errors.append(f"src/{package}/py.typed is missing; the package must ship its types")
    requirements = root / "requirements-test.txt"
    lines = requirements.read_text("utf-8").splitlines() if requirements.is_file() else []
    errors += [
        *check_standard(tool(root, "pyright"), coverage(root), transition(root)),
        *check_build(pyproject),
        *check_test_tools(lines),
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
        case _:
            sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
