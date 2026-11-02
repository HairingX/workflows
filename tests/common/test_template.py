"""Tests of how a repository is kept in agreement with the template."""

from pathlib import Path

import pytest

from template import BEGIN, COMMON, END, PREVIOUS_MARKERS, TEMPLATES, differences, files, main, shared_section, sources, sync


@pytest.fixture
def template(tmp_path: Path) -> Path:
    root = tmp_path / "template"
    (root / ".github" / "workflows").mkdir(parents=True)
    (root / ".github" / "workflows" / "tests.yml").write_text("name: Tests\n", "utf-8")
    (root / ".github" / "release.yml").write_text("changelog: {}\n", "utf-8")
    (root / "CLAUDE.md").write_text("## Shared\n\nThe rules.\n", "utf-8")
    return root


@pytest.fixture
def common(tmp_path: Path) -> Path:
    root = tmp_path / "common"
    (root / ".github" / "rulesets").mkdir(parents=True)
    (root / ".github" / "rulesets" / "branch-names.json").write_text("{}\n", "utf-8")
    return root


def _repository(root: Path) -> Path:
    (root / ".github" / "workflows").mkdir(parents=True)
    (root / ".github" / "scripts").mkdir()
    (root / ".github" / "scripts" / "old.py").write_text("", "utf-8")
    (root / ".github" / "release-drafter.yml").write_text("template: x\n", "utf-8")
    (root / ".github" / "workflows" / "release-dev.yml").write_text("old\n", "utf-8")
    (root / ".github" / "workflows" / "tests.yml").write_text("name: Old\n", "utf-8")
    (root / "CLAUDE.md").write_text("# Conventions\n\nOur own.\n", "utf-8")
    return root


def test_the_section_is_not_one_of_the_copied_files(template: Path, common: Path) -> None:
    assert files(template, common) == [
        ".github/release.yml",
        ".github/rulesets/branch-names.json",
        ".github/workflows/tests.yml",
    ]


def test_every_difference_is_reported(tmp_path: Path, template: Path, common: Path) -> None:
    root = _repository(tmp_path / "repository")
    assert list(differences(root, template, common)) == [
        ".github/release.yml is missing; the template has it",
        ".github/rulesets/branch-names.json is missing; the template has it",
        ".github/workflows/tests.yml differs from the template's",
        ".github/workflows/release-dev.yml is no workflow of the template; workflows are shared, not added per repository",
        ".github/scripts must not exist; it comes from HairingX/workflows",
        ".github/release-drafter.yml must not exist; it comes from HairingX/workflows",
        f"CLAUDE.md lacks the shared section between {BEGIN!r} and {END!r}",
    ]


def test_sync_brings_the_repository_into_agreement(tmp_path: Path, template: Path, common: Path) -> None:
    root = _repository(tmp_path / "repository")
    sync(root, template, common)
    assert list(differences(root, template, common)) == []
    assert not (root / ".github" / "workflows" / "release-dev.yml").exists()
    assert not (root / ".github" / "release-drafter.yml").exists()
    claude = (root / "CLAUDE.md").read_text("utf-8")
    assert claude == f"# Conventions\n\nOur own.\n\n{shared_section(template)}\n"


def test_sync_replaces_an_outdated_section_and_keeps_what_follows(tmp_path: Path, template: Path, common: Path) -> None:
    root = _repository(tmp_path / "repository")
    (root / "CLAUDE.md").write_text(f"# Own\n\n{BEGIN}\nold\n{END}\n\nAfter.\n", "utf-8")
    assert "the shared section of CLAUDE.md differs from the template's" in list(differences(root, template, common))
    sync(root, template, common)
    assert (root / "CLAUDE.md").read_text("utf-8") == f"# Own\n\n{shared_section(template)}\n\nAfter.\n"


def test_the_shared_template_is_complete() -> None:
    assert (TEMPLATES["ha"] / "CLAUDE.md").is_file()
    assert {path for path in files(TEMPLATES["ha"]) if path.startswith(".github/workflows/")} == {
        ".github/workflows/close-inactive-issues.yml",
        ".github/workflows/harness-merge.yml",
        ".github/workflows/library-released.yml",
        ".github/workflows/release-drafter.yml",
        ".github/workflows/release.yml",
        ".github/workflows/scorecards.yml",
        ".github/workflows/test-build-cleanup.yml",
        ".github/workflows/test-build.yml",
        ".github/workflows/tests.yml",
        ".github/workflows/validate.yml",
    }


def test_the_cards_template_is_complete() -> None:
    assert (TEMPLATES["card"] / "CLAUDE.md").is_file()
    assert files(TEMPLATES["card"]) == [
        ".github/dependabot.yml",
        ".github/release.yml",
        ".github/rulesets/branch-names.json",
        ".github/rulesets/main.json",
        ".github/workflows/close-inactive-issues.yml",
        ".github/workflows/release-drafter.yml",
        ".github/workflows/release.yml",
        ".github/workflows/test-build-cleanup.yml",
        ".github/workflows/test-build.yml",
        ".github/workflows/tests.yml",
        ".github/workflows/validate.yml",
    ]


def test_the_command_line_checks_and_syncs_a_card(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = tmp_path / "card"
    root.mkdir()
    with pytest.raises(SystemExit):
        main(["check", "card", str(root)])
    main(["sync", "card", str(root)])
    main(["check", "card", str(root)])
    assert "The repository agrees with the template." in capsys.readouterr().out


def test_sync_refuses_a_section_with_one_marker(tmp_path: Path, template: Path, common: Path) -> None:
    root = _repository(tmp_path / "repository")
    (root / "CLAUDE.md").write_text(f"# Own\n\n{BEGIN}\nhalf a section\n", "utf-8")
    with pytest.raises(SystemExit, match="only one of the markers"):
        sync(root, template, common)


def test_a_file_in_both_templates_is_refused(template: Path, common: Path) -> None:
    (common / ".github" / "release.yml").write_text("changelog: {}\n", "utf-8")
    with pytest.raises(SystemExit, match="in both"):
        sources(template, common)


def test_sync_replaces_the_section_under_the_former_markers(tmp_path: Path, template: Path, common: Path) -> None:
    root = _repository(tmp_path / "repository")
    (begin, _), (end, _), _ = PREVIOUS_MARKERS
    (root / "CLAUDE.md").write_text(f"# Own\n\n{begin}\nold\n{end}\n", "utf-8")
    sync(root, template, common)
    assert (root / "CLAUDE.md").read_text("utf-8") == f"# Own\n\n{shared_section(template)}\n"


def test_the_common_template_holds_what_every_kind_of_repository_shares() -> None:
    assert sorted(path.relative_to(COMMON).as_posix() for path in COMMON.rglob("*") if path.is_file()) == [
        ".github/release.yml",
        ".github/rulesets/branch-names.json",
        ".github/workflows/close-inactive-issues.yml",
        ".github/workflows/release-drafter.yml",
    ]
