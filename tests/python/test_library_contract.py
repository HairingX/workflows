"""Tests of what every library's repository promises."""

from pathlib import Path

import pytest

from library_contract import PYTHON_VERSIONS, check, check_build, check_test_tools

PYPROJECT = """[build-system]
requires = ["setuptools>=80", "setuptools-scm[simple]>=9.2"]
build-backend = "setuptools.build_meta"

[project]
name = "demo_lib"
dynamic = ["version"]
requires-python = ">=3.14"

[tool.pyright]
typeCheckingMode = "strict"
"""
TEST_TOOLS = "pyright==1.1.414\npytest==9.1.1\npytest-cov==7.0.0  # coverage\n"


def _library(root: Path, *, pyproject: str = PYPROJECT, typed: bool = True, tools: str = TEST_TOOLS) -> Path:
    (root / "src" / "demo_lib").mkdir(parents=True)
    (root / "src" / "demo_lib" / "__init__.py").write_text("", "utf-8")
    if typed:
        (root / "src" / "demo_lib" / "py.typed").write_text("", "utf-8")
    (root / "pyproject.toml").write_text(pyproject, "utf-8")
    (root / "requirements-test.txt").write_text(tools, "utf-8")
    return root


def test_a_library_to_the_standard_breaks_no_promise(tmp_path: Path) -> None:
    assert check(_library(tmp_path)) == []


def test_the_tests_run_only_on_the_python_home_assistant_runs_on() -> None:
    assert PYTHON_VERSIONS == ("3.14",)


def test_a_package_without_its_types_is_refused(tmp_path: Path) -> None:
    assert check(_library(tmp_path, typed=False)) == [
        "src/demo_lib/py.typed is missing; the package must ship its types"
    ]


def test_the_version_comes_only_from_the_tag() -> None:
    assert list(
        check_build({"build-system": {"requires": ["setuptools"]}, "project": {"version": "1.0", "requires-python": ">=3.11"}})
    ) == [
        "[build-system] must require setuptools-scm, which works the version out from the tag",
        "[project] must not state a version; the release's tag is the version",
        '[project] dynamic must list "version"',
        '[project] requires-python must be ">=3.14", the oldest Python the tests run',
    ]


def test_a_build_requirement_that_is_none_is_reported() -> None:
    errors = list(check_build({"build-system": {"requires": ["not a requirement!"]}}))
    assert "[build-system] requires 'not a requirement!', which is no requirement" in errors


def test_every_test_tool_is_pinned_and_the_shared_ones_are_there() -> None:
    assert list(check_test_tools(["-e .", "", "# note", "pytest>=9", "x y z", "pyright==1.1.414"])) == [
        "requirements-test.txt must pin pytest with ==",
        "requirements-test.txt: 'x y z' is no requirement",
        "requirements-test.txt must pin pytest-cov",
    ]


def test_a_library_without_test_tools_is_told_which_to_pin(tmp_path: Path) -> None:
    root = _library(tmp_path)
    (root / "requirements-test.txt").unlink()
    assert check(root) == [f"requirements-test.txt must pin {name}" for name in ("pyright", "pytest", "pytest-cov")]


def test_a_transition_relaxes_the_standard_but_not_the_build(tmp_path: Path) -> None:
    pyproject = PYPROJECT.replace('typeCheckingMode = "strict"', 'typeCheckingMode = "standard"')
    pyproject += '\n[tool.hairingx-workflows]\ntransition = "Typed module by module."\ncoverage = 50\n'
    assert check(_library(tmp_path, pyproject=pyproject)) == []


@pytest.mark.parametrize("arguments", [[], ["a", "b"]])
def test_the_command_line_takes_one_repository(arguments: list[str]) -> None:
    from library_contract import main

    with pytest.raises(SystemExit):
        main(arguments)


def test_the_command_line_reports_every_broken_promise(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from library_contract import main

    with pytest.raises(SystemExit):
        main([str(_library(tmp_path, typed=False))])
    assert "::error::src/demo_lib/py.typed is missing" in capsys.readouterr().out
    main([str(_library(tmp_path / "other"))])
    assert "Every promise of the repository holds." in capsys.readouterr().out
