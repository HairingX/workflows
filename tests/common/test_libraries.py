"""Tests of how a development branch takes its libraries from their branch of the same name."""

import json
from pathlib import Path

import pytest

import libraries
from libraries import branch_requirements, replace_manifest, replace_requirements


def _repository(root: Path, names: list[str]) -> Path:
    listed = ", ".join(f'"{name}"' for name in names)
    (root / "pyproject.toml").write_text(
        f"[tool.ha-integration-workflows]\nlibraries = [{listed}]\n", "utf-8"
    )
    return root


def test_a_library_with_the_branch_is_pinned_to_its_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    heads = {"https://github.com/Owner/device_lib": "abc123"}

    def head(repository: str, branch: str) -> str | None:
        return heads.get(repository)

    monkeypatch.setattr(libraries, "head", head)
    root = _repository(tmp_path, ["base_lib", "device_lib"])
    assert branch_requirements(root, "Owner", "fix/x") == [
        "device_lib @ https://github.com/Owner/device_lib/archive/abc123.tar.gz"
    ]


def test_the_branch_is_looked_up_by_its_full_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: list[tuple[str, str]] = []

    def head(repository: str, branch: str) -> None:
        asked.append((repository, branch))

    monkeypatch.setattr(libraries, "head", head)
    branch_requirements(_repository(tmp_path, ["base_lib"]), "Owner", "feature/a/b")
    assert asked == [("https://github.com/Owner/base_lib", "feature/a/b")]


def test_a_dependabot_branch_takes_no_library_from_a_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def head(repository: str, branch: str) -> str:
        return "abc123"

    monkeypatch.setattr(libraries, "head", head)
    root = _repository(tmp_path, ["base_lib"])
    assert branch_requirements(root, "Owner", "dependabot/pip/beautifulsoup4-4.15.0") == []


def test_a_branch_library_takes_the_place_of_its_pin() -> None:
    lines = [
        "# Pinned.",
        "pytest-homeassistant==2026.11.0",
        "Device-Lib==1.4.0  # the manifest's",
        "base_lib==2.0.0",
    ]
    branch = "device_lib @ https://github.com/Owner/device_lib/archive/abc.tar.gz"
    assert replace_requirements(lines, [branch]) == [
        "# Pinned.",
        "pytest-homeassistant==2026.11.0",
        "base_lib==2.0.0",
        branch,
    ]


def test_without_branch_libraries_the_requirements_stay() -> None:
    lines = ["a==1", "b==2"]
    assert replace_requirements(lines, []) == lines


def test_the_manifest_requires_the_branch_library_and_keeps_its_indentation() -> None:
    manifest = json.dumps({"domain": "demo", "requirements": ["device_lib==1.0.0", "other==2"]}, indent=4)
    branch = "device_lib @ https://github.com/Owner/device_lib/archive/abc.tar.gz"
    replaced = replace_manifest(manifest, [branch])
    assert json.loads(replaced)["requirements"] == [branch, "other==2"]
    assert '\n    "domain"' in replaced


def test_without_branch_libraries_the_manifest_stays_byte_for_byte() -> None:
    manifest = '{\n  "domain": "demo",\n  "requirements": ["device_lib==1.0.0"]\n}'
    assert replace_manifest(manifest, []) == manifest


def test_the_manifest_keeps_its_letters() -> None:
    manifest = json.dumps({"name": "Dørklokke", "requirements": ["device_lib==1.0.0"]}, indent=2)
    branch = "device_lib @ https://github.com/Owner/device_lib/archive/abc.tar.gz"
    assert '"Dørklokke"' in replace_manifest(manifest, [branch])
