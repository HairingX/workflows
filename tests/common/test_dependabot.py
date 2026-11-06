"""Tests of what becomes of Dependabot's pull requests."""

from typing import Any

import pytest

from dependabot import HARNESSES, MAJOR, decide, harness_home_assistant, main, pre_release

HARNESS, REPLACED = HARNESSES

PYPI: dict[str, list[str] | None] = {
    f"{HARNESS}/2027.1.0b2": ["pytest==9.1.1", "homeassistant==2027.1.0b2"],
    f"{HARNESS}/2027.1.0": ["homeassistant==2027.1.0", "pytest==9.1.1"],
    f"{HARNESS}/2027.1.1": None,
    f"{REPLACED}/0.13.380": ["pytest==9.1.1", "homeassistant==2026.11.0b2"],
    f"{REPLACED}/0.13.381": ["homeassistant==2026.11.0", "pytest==9.1.1"],
}


def _fetch(url: str) -> dict[str, Any]:
    return {"info": {"requires_dist": PYPI[url.removeprefix("https://pypi.org/pypi/").removesuffix("/json")]}}


def test_an_update_that_is_no_new_major_version_is_merged() -> None:
    assert decide("version-update:semver-minor", "pytest, pyright", "", _fetch) == ("merge", "")
    assert decide("version-update:semver-patch", "pytest", "9.2.1", _fetch) == ("merge", "")


def test_a_new_major_version_is_left_to_the_owner() -> None:
    assert decide(MAJOR, "typescript", "7.0.2", _fetch) == ("owner", "it is a new major version")


def test_the_harness_made_for_a_final_home_assistant_release_is_merged() -> None:
    assert decide("version-update:semver-minor", HARNESS, "2027.1.0", _fetch) == ("merge", "")
    assert decide("version-update:semver-patch", REPLACED, "0.13.381", _fetch) == ("merge", "")


def test_the_harness_of_a_new_home_assistant_year_is_merged() -> None:
    """Its major version is Home Assistant's year, which says nothing about what changed."""
    assert decide(MAJOR, HARNESS, "2027.1.0", _fetch) == ("merge", "")


def test_a_new_major_version_beside_the_harness_is_left_to_the_owner() -> None:
    assert decide(MAJOR, f"{HARNESS}, typescript", "2027.1.0", _fetch) == ("owner", "it is a new major version")


def test_the_harness_made_for_a_home_assistant_beta_is_closed() -> None:
    assert decide("version-update:semver-minor", HARNESS, "2027.1.0b2", _fetch) == (
        "close",
        f"{HARNESS} 2027.1.0b2 is made for Home Assistant 2027.1.0b2, a pre-release",
    )
    assert decide("version-update:semver-patch", REPLACED, "0.13.380", _fetch) == (
        "close",
        f"{REPLACED} 0.13.380 is made for Home Assistant 2026.11.0b2, a pre-release",
    )


def test_a_harness_that_names_no_home_assistant_is_left_to_the_owner() -> None:
    assert decide("version-update:semver-patch", HARNESS, "2027.1.1", _fetch) == (
        "owner",
        f"{HARNESS} 2027.1.1 names no Home Assistant release",
    )
    assert harness_home_assistant(HARNESS, "2027.1.1", _fetch) is None


@pytest.mark.parametrize("version", ["2026.11.0b0", "2026.11.0rc1", "2026.11.0a3", "2026.11.0.dev20261101", "2026.11.0dev1"])
def test_a_pre_release_is_recognised(version: str) -> None:
    assert pre_release(version)


@pytest.mark.parametrize("version", ["2026.11.0", "2026.11.1", "2026.10.4"])
def test_a_final_release_is_no_pre_release(version: str) -> None:
    assert not pre_release(version)


def test_the_command_line_prints_the_outputs(capsys: pytest.CaptureFixture[str]) -> None:
    main(["decide", "version-update:semver-minor", "pytest", "9.2.0"])
    assert capsys.readouterr().out == "action=merge\nwhy=\n"


def test_the_command_line_refuses_other_arguments() -> None:
    with pytest.raises(SystemExit):
        main(["merge"])
