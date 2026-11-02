"""What becomes of one of Dependabot's pull requests.

    dependabot.py decide UPDATE_TYPE NAMES NEW_VERSION
        prints action=merge, action=owner or action=close, and why=..., for the update of the
        comma-separated NAMES to NEW_VERSION, of Dependabot's UPDATE_TYPE

An update that is no new major version is merged once its checks pass. The Home Assistant test
harness is released for every Home Assistant version, betas included, under version numbers that
do not say which: one made for a pre-release is closed. A new major version is left to the owner.

The standard library only: it runs before any Python is set up.
"""

import json
import re
import sys
import urllib.request
from collections.abc import Callable
from typing import Any, cast

HARNESS = "pytest-homeassistant-custom-component"
"""The Home Assistant test harness, released for one Home Assistant version each."""
MAJOR = "version-update:semver-major"
HOME_ASSISTANT = re.compile(r"^homeassistant\s*==\s*([^\s;]+)", re.I)
PRE_RELEASE = re.compile(r"\d(a|b|rc|\.?dev)\d*", re.I)

Fetch = Callable[[str], dict[str, Any]]


def _pypi(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=60) as response:
        return cast(dict[str, Any], json.load(response))


def harness_home_assistant(version: str, fetch: Fetch) -> str | None:
    """The Home Assistant release the test harness `version` is made for, None if it names none."""
    info = cast(dict[str, Any], fetch(f"https://pypi.org/pypi/{HARNESS}/{version}/json")["info"])
    for line in cast(list[str], info.get("requires_dist") or []):
        found = HOME_ASSISTANT.match(line)
        if found is not None:
            return found[1]
    return None


def pre_release(version: str) -> bool:
    """Whether the PEP 440 `version` is an alpha, beta, release candidate or development release."""
    return PRE_RELEASE.search(version) is not None


def decide(update_type: str, names: str, new_version: str, fetch: Fetch) -> tuple[str, str]:
    """What becomes of the update, and why where it is not merged."""
    dependencies = [name.strip() for name in names.split(",") if name.strip()]
    if HARNESS in dependencies:
        home_assistant = harness_home_assistant(new_version, fetch)
        if home_assistant is None:
            return "owner", f"{HARNESS} {new_version} names no Home Assistant release"
        if pre_release(home_assistant):
            return "close", f"{HARNESS} {new_version} is made for Home Assistant {home_assistant}, a pre-release"
    if update_type == MAJOR:
        return "owner", "it is a new major version"
    return "merge", ""


def main(arguments: list[str]) -> None:
    """Print what `arguments` asks for."""
    match arguments:
        case ["decide", update_type, names, new_version]:
            action, why = decide(update_type, names, new_version, _pypi)
            print(f"action={action}")
            print(f"why={why}")
        case _:
            sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
