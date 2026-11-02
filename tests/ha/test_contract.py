"""Tests of what every integration's repository promises."""

import json
import sys
from pathlib import Path

from packaging.specifiers import SpecifierSet

import pytest

import contract
from contract import (
    QUALITY_SCALE_RULES,
    installed_version,
    check,
    check_hacs,
    check_manifest,
    check_minimum,
    check_quality_scale,
    check_requirements,
    check_test_pins,
    check_translations,
    HomeAssistant,
    home_assistant,
    home_assistant_pins,
    minimum,
    minimum_test_pins,
    refused,
    requirement_closure,
    released,
)


def test_a_library_built_from_a_branch_is_not_a_release() -> None:
    assert released("0.2.0")
    assert released("0.2.0rc1")
    assert not released("0.2.1.dev3+g1c7097c")
    assert not released("0.2.1+local")
    assert not released("not a version")


def test_the_manifest_says_0_0_0() -> None:
    assert list(check_manifest({"version": "0.0.0"})) == []
    assert list(check_manifest({"version": "0.2.8"})) == [
        "manifest.json says version '0.2.8'; it must say '0.0.0'"
    ]


def test_hacs_installs_the_domains_zip_on_the_home_assistant_tested() -> None:
    hacs = {"zip_release": True, "filename": "demo.zip", "homeassistant": "2026.10.4"}
    assert list(check_hacs(hacs, "demo", "2026.10.4")) == []


def test_every_way_hacs_json_can_be_wrong_is_reported() -> None:
    hacs = {"filename": "other.zip", "homeassistant": "2026.11.0"}
    assert list(check_hacs(hacs, "demo", "2026.10.4")) == [
        "hacs.json must set zip_release to true",
        "hacs.json names the zip 'other.zip'; it must be 'demo.zip'",
        "hacs.json requires Home Assistant '2026.11.0', newer than the '2026.10.4' the tests run",
    ]


def test_hacs_json_may_require_a_home_assistant_older_than_the_one_tested() -> None:
    hacs = {"zip_release": True, "filename": "demo.zip", "homeassistant": "2026.10.2"}
    assert list(check_hacs(hacs, "demo", "2026.11.1")) == []


@pytest.mark.parametrize("required", [None, "", "latest", 2026])
def test_hacs_json_must_name_the_oldest_home_assistant_supported(required: object) -> None:
    hacs = {"zip_release": True, "filename": "demo.zip", "homeassistant": required}
    assert list(check_hacs(hacs, "demo", "2026.10.4")) == [
        "hacs.json must give the oldest Home Assistant the integration supports in homeassistant, "
        "such as '2026.10.4'"
    ]


def test_without_home_assistant_installed_no_requirement_holds() -> None:
    hacs = {"zip_release": True, "filename": "demo.zip", "homeassistant": "2026.10.4"}
    assert list(check_hacs(hacs, "demo", None)) == [
        "hacs.json requires Home Assistant '2026.10.4', newer than the None the tests run"
    ]


def test_the_oldest_home_assistant_supported_is_tested_only_when_older() -> None:
    assert minimum({"homeassistant": "2026.10.2"}, "2026.11.1") == "2026.10.2"
    assert minimum({"homeassistant": "2026.11.1"}, "2026.11.1") is None
    assert minimum({"homeassistant": "2026.12.0"}, "2026.11.1") is None
    assert minimum({"homeassistant": "latest"}, "2026.11.1") is None
    assert minimum({"homeassistant": "2026.10.2"}, None) is None


def test_the_oldest_home_assistant_runs_its_own_harness_and_its_own_integrations_pins() -> None:
    pinned = [
        "# The harness pins the Home Assistant release the tests run.",
        "pytest-homeassistant-custom-component==0.13.380",
        "pyright==1.1.414  # the type check",
        "",
        "device-lib==1.2.0",
        "qrcode==8.3",
        "aiohttp==3.14.0",
        "other-lib @ https://github.com/Owner/other-lib/archive/feature.tar.gz",
        "-c constraints.txt",
    ]
    core = HomeAssistant(dependencies=frozenset({"aiohttp"}), pins={"qrcode": frozenset({"8.1", "8.2"})})
    assert minimum_test_pins(pinned, core, "0.13.373") == [
        "pytest-homeassistant-custom-component==0.13.373",
        "pyright==1.1.414",
        "device-lib==1.2.0",
        "qrcode==8.2",
        "other-lib @ https://github.com/Owner/other-lib/archive/feature.tar.gz",
        "-c constraints.txt",
    ]


def test_without_a_harness_installed_its_pin_is_kept() -> None:
    pinned = ["pytest-homeassistant-custom-component==0.13.380"]
    assert minimum_test_pins(pinned, HomeAssistant(), None) == pinned


def test_the_oldest_home_assistant_supported_is_the_one_tested_and_accepts_the_requirements() -> None:
    core = HomeAssistant(pins={"qrcode": frozenset({"8.2"})})
    assert list(check_minimum({"homeassistant": "2026.10.2"}, "2026.10.2", ["device-lib==1.2.0", "qrcode>=8.0"], core)) == []


def test_the_oldest_home_assistant_supported_must_be_the_one_tested() -> None:
    assert list(check_minimum({"homeassistant": "2026.10.2"}, "2026.11.1", [], HomeAssistant())) == [
        "hacs.json requires Home Assistant '2026.10.2', but the tests of the oldest supported run '2026.11.1'"
    ]


def test_a_requirement_the_oldest_home_assistant_supported_refuses_is_reported() -> None:
    core = HomeAssistant(pins={"qrcode": frozenset({"7.4"})})
    assert list(check_minimum({"homeassistant": "2026.10.2"}, "2026.10.2", ["qrcode>=8.0"], core)) == [
        "the manifest's 'qrcode>=8.0' excludes qrcode 7.4, which Home Assistant's own integrations pin"
    ]


def test_a_requirement_home_assistant_accepts_is_not_refused() -> None:
    assert refused("device-lib==1.2.0", HomeAssistant()) is None


def test_a_requirement_pinned_installed_and_pinned_for_the_tests_holds() -> None:
    assert list(check_requirements(["Device_Lib==1.2.0"], ["Device_Lib==1.2.0"], {"device-lib": "1.2.0"}, HomeAssistant())) == []


def test_a_requirement_must_be_pinned_exactly() -> None:
    assert list(check_requirements(["lxml>=5.0.0"], [], {"lxml": "5.3.0"}, HomeAssistant())) == [
        "the manifest's requirement 'lxml>=5.0.0' must pin one version with =="
    ]


def test_the_tests_must_run_the_version_pinned() -> None:
    assert list(check_requirements(["lib==1.2.0"], ["lib==1.2.0"], {"lib": "1.3.0"}, HomeAssistant())) == [
        "the manifest pins 'lib==1.2.0', but the tests run lib 1.3.0"
    ]


def test_requirements_test_txt_must_pin_what_the_manifest_does() -> None:
    assert list(check_requirements(["lib==1.2.0"], ["# lib==1.2.0", "other==1"], {"lib": "1.2.0"}, HomeAssistant())) == [
        "requirements-test.txt must pin 'lib==1.2.0', as the manifest does"
    ]


def test_a_library_from_a_branch_is_not_held_to_its_pin() -> None:
    assert list(check_requirements(["lib==1.2.0"], ["lib==1.2.0"], {"lib": "1.2.1.dev3+gabc"}, HomeAssistant())) == []


def test_a_requirement_not_installed_is_reported() -> None:
    assert list(check_requirements(["lib==1.2.0"], ["lib==1.2.0"], {"lib": None}, HomeAssistant())) == [
        "lib is required by the manifest but not installed"
    ]


def _all_done() -> dict[str, object]:
    return {rule: "done" for rule in QUALITY_SCALE_RULES}


def test_a_quality_scale_stating_every_rule_holds() -> None:
    rules = _all_done()
    rules["discovery"] = {"status": "exempt", "comment": "The device cannot be discovered."}
    assert list(check_quality_scale(rules)) == []


def test_a_rule_missing_or_unknown_is_reported() -> None:
    rules = _all_done()
    del rules["brands"]
    rules["made-up"] = "done"
    assert list(check_quality_scale(rules)) == [
        "quality_scale.yaml does not state the rule brands",
        "quality_scale.yaml states made-up, which is no rule of the quality scale",
    ]


def test_a_rule_not_done_needs_a_reason() -> None:
    rules = _all_done()
    rules["discovery"] = {"status": "todo"}
    rules["brands"] = {"status": "maybe", "comment": "?"}
    rules["devices"] = "todo"
    assert list(check_quality_scale(rules)) == [
        "quality_scale.yaml: brands has status 'maybe'",
        "quality_scale.yaml: devices must be done, or have a status and a comment",
        "quality_scale.yaml: discovery is todo without a comment saying why",
    ]


def test_the_rules_are_those_hassfest_lists() -> None:
    assert len(QUALITY_SCALE_RULES) == 54


def test_every_translation_holds_the_keys_english_has() -> None:
    english = {"config": {"step": {"user": {"title": "Set up"}}}, "entity": {}}
    danish = {"config": {"step": {"user": {"title": "Opsæt", "extra": "x"}}}}
    assert list(check_translations({"en": english, "da": danish})) == [
        "translations/da.json lacks entity",
        "translations/da.json has config.step.user.extra, which English does not",
    ]


def test_english_must_be_there() -> None:
    assert list(check_translations({"da": {}})) == ["translations/en.json is missing"]


def _repository(root: Path) -> Path:
    integration = root / "custom_components" / "demo"
    (integration / "translations").mkdir(parents=True)
    (integration / "manifest.json").write_text(
        json.dumps({"domain": "demo", "version": "0.0.0", "requirements": ["lib==1.2.0"]}), "utf-8"
    )
    (integration / "translations" / "en.json").write_text('{"title": "Demo"}', "utf-8")
    (integration / "translations" / "da.json").write_text('{"title": "Demo"}', "utf-8")
    rules = "\n".join(f"  {rule}: done" for rule in sorted(QUALITY_SCALE_RULES))
    (integration / "quality_scale.yaml").write_text(f"rules:\n{rules}\n", "utf-8")
    (root / "hacs.json").write_text(
        json.dumps({"zip_release": True, "filename": "demo.zip", "homeassistant": "2026.10.4"}), "utf-8"
    )
    (root / "requirements-test.txt").write_text("lib==1.2.0\n", "utf-8")
    (root / "pyproject.toml").write_text('[tool.pyright]\ntypeCheckingMode = "strict"\n', "utf-8")
    return root


def test_a_repository_keeping_every_promise_has_no_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    versions = {"lib": "1.2.0", "homeassistant": "2026.10.4"}
    monkeypatch.setattr(contract, "_installed", versions.get)
    assert check(_repository(tmp_path)) == []


def test_a_repository_without_a_quality_scale_is_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    versions = {"lib": "1.2.0", "homeassistant": "2026.10.4"}
    monkeypatch.setattr(contract, "_installed", versions.get)
    root = _repository(tmp_path)
    (root / "custom_components" / "demo" / "quality_scale.yaml").unlink()
    errors = check(root)
    assert errors[0] == "demo/quality_scale.yaml is missing"
    assert len(errors) == 1 + len(QUALITY_SCALE_RULES)


def test_a_pin_with_a_comment_is_read_without_it() -> None:
    pinned = ["lib==1.2.0  # the manifest's", "other @ https://example.invalid/x.tar.gz"]
    assert list(check_requirements(["lib==1.2.0"], pinned, {"lib": "1.2.0"}, HomeAssistant())) == []


def test_home_assistants_requirements_are_read_from_its_package(tmp_path: Path) -> None:
    for name, requirements in {"scrape": ["beautifulsoup4==4.13.3", "lxml==6.1.2"], "other": ["lxml>=5"]}.items():
        (tmp_path / "components" / name).mkdir(parents=True)
        (tmp_path / "components" / name / "manifest.json").write_text(json.dumps({"requirements": requirements}), "utf-8")
    (tmp_path / "package_constraints.txt").write_text("# Constraints\npymodbus==3.11.2\n", "utf-8")
    core = home_assistant(tmp_path, ["requests==2.34.2", "colorlog==6.9; extra == 'dev'"])
    assert core.dependencies == {"requests"}
    assert core.pins == {"beautifulsoup4": {"4.13.3"}, "lxml": {"6.1.2"}}
    assert {name: str(spec) for name, spec in core.constraints.items()} == {"pymodbus": "==3.11.2"}


SCRAPE = HomeAssistant(
    dependencies=frozenset({"requests"}),
    pins={"beautifulsoup4": frozenset({"4.13.3"}), "lxml": frozenset({"6.1.2"})},
)


def test_a_package_home_assistant_installs_is_not_listed() -> None:
    assert list(check_requirements(["requests>=2"], [], {"requests": "2.34.2"}, SCRAPE)) == [
        "requests is a dependency of Home Assistant itself; the manifest must not list it"
    ]


def test_a_package_home_assistants_integrations_pin_is_required_at_a_minimum() -> None:
    assert list(check_requirements(["lxml==6.1.2"], ["lxml==6.1.2"], {"lxml": "6.1.2"}, SCRAPE)) == [
        "the manifest pins 'lxml==6.1.2', a package Home Assistant's own integrations use (6.1.2); "
        "require a minimum version instead, such as 'lxml>=6.1.2'"
    ]


def test_a_minimum_that_admits_home_assistants_version_holds() -> None:
    pinned = ["beautifulsoup4==4.13.3", "lxml==6.1.2"]
    installed = {"beautifulsoup4": "4.13.3", "lxml": "6.1.2"}
    assert list(check_requirements(["beautifulsoup4>=4.12.0", "lxml>=5.0.0"], pinned, installed, SCRAPE)) == []


def test_a_minimum_above_home_assistants_version_is_refused() -> None:
    assert list(check_requirements(["lxml>=6.2"], ["lxml==6.1.2"], {"lxml": "6.1.2"}, SCRAPE)) == [
        "the manifest's 'lxml>=6.2' excludes lxml 6.1.2, which Home Assistant's own integrations pin"
    ]


def test_the_tests_run_home_assistants_version_of_a_shared_package() -> None:
    assert list(check_requirements(["lxml>=5"], ["lxml==6.1.3"], {"lxml": "6.1.3"}, SCRAPE)) == [
        "requirements-test.txt must pin lxml to the version Home Assistant's own integrations pin (6.1.2)"
    ]
    assert list(check_requirements(["lxml>=5"], ["lxml==6.1.2"], {"lxml": "6.1.3"}, SCRAPE)) == [
        "the tests run lxml 6.1.3, not the version Home Assistant's own integrations pin"
    ]


def test_a_pin_home_assistants_constraints_exclude_is_refused() -> None:
    core = HomeAssistant(constraints={"pymodbus": SpecifierSet("==3.11.2")})
    assert list(check_requirements(["pymodbus==3.9.0"], ["pymodbus==3.9.0"], {"pymodbus": "3.9.0"}, core)) == [
        "the manifest pins 'pymodbus==3.9.0', which Home Assistant's package constraints (pymodbus==3.11.2) exclude"
    ]


def test_a_library_installed_from_a_url_is_no_release(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A branch's source download has no tags, and its version can read as a release, such as 0.0."""
    site = tmp_path / "site"
    for name, direct in (("from_branch", True), ("from_index", False)):
        info = site / f"{name}-0.0.dist-info"
        info.mkdir(parents=True)
        (info / "METADATA").write_text(f"Metadata-Version: 2.1\nName: {name}\nVersion: 0.0\n", "utf-8")
        if direct:
            (info / "direct_url.json").write_text('{"url": "https://example.invalid/a.tar.gz", "archive_info": {}}', "utf-8")
    monkeypatch.setattr(sys, "path", [str(site), *sys.path])
    assert installed_version("from_branch") == "0.0+url"
    assert not released("0.0+url")
    assert installed_version("from_index") == "0.0"
    assert installed_version("not_installed_anywhere") is None


def test_the_tests_run_home_assistants_version_of_a_librarys_requirement() -> None:
    pinned = ["aula_lib==1.0.0", "beautifulsoup4==4.13.3", "lxml==6.1.2", "pyright==1.1.414"]
    assert list(check_test_pins(["aula_lib==1.0.0"], pinned, SCRAPE)) == []


def test_a_librarys_requirement_pinned_past_home_assistants_version_is_refused() -> None:
    assert list(check_test_pins([], ["beautifulsoup4==4.15.0"], SCRAPE)) == [
        "requirements-test.txt pins beautifulsoup4 4.15.0, but Home Assistant's own integrations "
        "pin 4.13.3, the version the tests must run"
    ]


def test_a_librarys_requirement_its_constraints_exclude_is_refused() -> None:
    core = HomeAssistant(constraints={"pymodbus": SpecifierSet(">=3.11")})
    assert list(check_test_pins([], ["pymodbus==3.9.0", "pymodbus-extra==1"], core)) == [
        "requirements-test.txt pins pymodbus 3.9.0, which Home Assistant's package constraints "
        "(pymodbus>=3.11) exclude"
    ]


def test_the_manifests_own_requirements_and_unpinned_lines_are_left_to_their_check() -> None:
    pinned = ["lxml==6.1.3", "beautifulsoup4>=4", "lib @ https://example.com/lib.tar.gz"]
    assert list(check_test_pins(["lxml>=5"], pinned, SCRAPE)) == []


REQUIRES: dict[str, list[str]] = {
    "aula-lib": ["beautifulsoup4>=4.12", "mitid-lib>=0.0.1", "requests>=2.31"],
    "mitid-lib": ["lxml>=5", "beautifulsoup4>=4.12", 'pytest; extra == "test"', 'colorama; sys_platform == "win32"'],
    "beautifulsoup4": ["soupsieve>1.2"],
}


def test_the_closure_follows_every_requirement_that_applies() -> None:
    assert requirement_closure(["aula_lib==1.0.0"], REQUIRES.get) == {
        "aula-lib", "beautifulsoup4", "lxml", "mitid-lib", "requests", "soupsieve"
    }


def test_home_assistants_pin_of_each_shared_package_is_installed() -> None:
    assert home_assistant_pins(["aula_lib==1.0.0"], SCRAPE, REQUIRES.get) == [
        "beautifulsoup4==4.13.3", "lxml==6.1.2"
    ]


def test_the_highest_of_several_pins_is_taken() -> None:
    core = HomeAssistant(pins={"lxml": frozenset({"6.1.2", "6.0.0"})})
    assert home_assistant_pins(["lxml>=5"], core, REQUIRES.get) == ["lxml==6.1.2"]


def test_a_package_home_assistant_requires_itself_is_left_to_it() -> None:
    core = HomeAssistant(dependencies=frozenset({"requests"}), pins={"requests": frozenset({"2.0"})})
    assert home_assistant_pins(["aula_lib==1.0.0"], core, REQUIRES.get) == []
