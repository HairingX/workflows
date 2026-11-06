"""Tests of the Python each Home Assistant tested requires."""

import json
from pathlib import Path
from typing import Any

import pytest

from pythons import harness_pin, lowest_python, pythons

PYPI: dict[str, dict[str, Any]] = {
    "pytest-homeassistant/2027.4.0": {
        "requires_dist": ["homeassistant==2027.4.0", "pytest==9.1.1", "habluetooth==7.1.2; extra == 'bluetooth'"]
    },
    "pytest-homeassistant-custom-component/0.13.390": {
        "requires_dist": ["fnv-hash-fast==1.6.0", "homeassistant==2027.4.0", "pytest==9.1.1"]
    },
    "homeassistant/2027.4.0": {"requires_python": ">=3.15.0"},
    "homeassistant/2026.10.2": {"requires_python": ">=3.14.2"},
}


def _fetch(url: str) -> dict[str, Any]:
    return {"info": PYPI[url.removeprefix("https://pypi.org/pypi/").removesuffix("/json")]}


def _repository(tmp_path: Path, home_assistant: str, harness: str = "Pytest_HomeAssistant == 2027.4.0") -> Path:
    (tmp_path / "requirements-test.txt").write_text(
        f"# The harness.\n{harness}  # pins Home Assistant\npyright==1.1.414\n", "utf-8"
    )
    (tmp_path / "hacs.json").write_text(json.dumps({"homeassistant": home_assistant}), "utf-8")
    return tmp_path


def test_each_home_assistant_runs_on_the_oldest_python_it_requires(tmp_path: Path) -> None:
    assert pythons(_repository(tmp_path, "2026.10.2"), _fetch) == {
        "harness": "pytest-homeassistant",
        "newest": "3.15",
        "minimum": "3.14",
    }


def test_no_python_is_named_for_the_oldest_when_it_is_the_newest(tmp_path: Path) -> None:
    assert pythons(_repository(tmp_path, "2027.4.0"), _fetch)["minimum"] == ""


def test_the_harness_it_replaced_is_still_accepted(tmp_path: Path) -> None:
    harness = "pytest_homeassistant_custom_component == 0.13.390"
    assert pythons(_repository(tmp_path, "2026.10.2", harness), _fetch) == {
        "harness": "pytest-homeassistant-custom-component",
        "newest": "3.15",
        "minimum": "3.14",
    }


def test_the_lowest_python_is_the_minor_version_of_the_lower_bound() -> None:
    assert lowest_python(">=3.14.2") == "3.14"
    assert lowest_python("<3.16,>=3.15") == "3.15"


def test_requires_python_without_a_lower_bound_is_refused() -> None:
    with pytest.raises(SystemExit, match="no lowest Python"):
        lowest_python(None)


def test_requirements_test_txt_must_pin_the_harness() -> None:
    assert harness_pin(["pyright==1.1.414", "pytest-homeassistant==2026.11.0"]) == ("pytest-homeassistant", "2026.11.0")
    assert harness_pin(["pytest-homeassistant-custom-component==0.13.375"]) == (
        "pytest-homeassistant-custom-component",
        "0.13.375",
    )
    with pytest.raises(SystemExit, match="must pin pytest-homeassistant with =="):
        harness_pin(["pytest-homeassistant>=2026.11"])


def test_a_harness_that_pins_no_home_assistant_is_refused(tmp_path: Path) -> None:
    PYPI["pytest-homeassistant/2027.4.1"] = {"requires_dist": None}
    (tmp_path / "requirements-test.txt").write_text("pytest-homeassistant==2027.4.1\n", "utf-8")
    with pytest.raises(SystemExit, match="pins no Home Assistant"):
        pythons(tmp_path, _fetch)
