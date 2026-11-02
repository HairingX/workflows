"""The Python each Home Assistant the tests run requires, read from PyPI.

    pythons.py ROOT     prints newest=X.Y, the oldest Python the Home Assistant of the test
                        harness pinned in requirements-test.txt runs on, and minimum=X.Y, that of
                        the oldest Home Assistant hacs.json supports, where it is another release

The standard library only: it runs before any Python is set up.
"""

import json
import re
import sys
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

HARNESS = re.compile(r"^\s*pytest[-_.]homeassistant[-_.]custom[-_.]component\s*==\s*([^\s#;]+)", re.I)
HOME_ASSISTANT = re.compile(r"^homeassistant\s*==\s*([^\s;]+)", re.I)
LOWEST = re.compile(r">=\s*(\d+)\.(\d+)")

Fetch = Callable[[str], dict[str, Any]]


def _pypi(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=60) as response:
        return cast(dict[str, Any], json.load(response))


def _info(fetch: Fetch, package: str, version: str) -> dict[str, Any]:
    return cast(dict[str, Any], fetch(f"https://pypi.org/pypi/{package}/{version}/json")["info"])


def lowest_python(requires_python: str | None) -> str:
    """The oldest Python minor version `requires_python` admits, such as 3.14 for >=3.14.2."""
    found = LOWEST.search(requires_python or "")
    if found is None:
        sys.exit(f"::error::no lowest Python in requires-python {requires_python!r}")
    return f"{found[1]}.{found[2]}"


def harness_pin(lines: list[str]) -> str:
    """The version of the test harness the lines of requirements-test.txt pin."""
    for line in lines:
        found = HARNESS.match(line)
        if found is not None:
            return found[1]
    sys.exit("::error::requirements-test.txt must pin pytest-homeassistant-custom-component with ==")


def pythons(root: Path, fetch: Fetch) -> dict[str, str]:
    """The Python of the newest Home Assistant tested, and of the oldest supported, by name."""
    harness = harness_pin((root / "requirements-test.txt").read_text("utf-8").splitlines())
    harness_info = _info(fetch, "pytest-homeassistant-custom-component", harness)
    requires = cast(list[str], harness_info.get("requires_dist") or [])
    newest = next((found[1] for line in requires if (found := HOME_ASSISTANT.match(line))), None)
    if newest is None:
        sys.exit(f"::error::pytest-homeassistant-custom-component {harness} pins no Home Assistant")
    found = {"newest": lowest_python(_info(fetch, "homeassistant", newest).get("requires_python"))}
    hacs = cast(dict[str, Any], json.loads((root / "hacs.json").read_text("utf-8")))
    oldest = hacs.get("homeassistant")
    found["minimum"] = (
        lowest_python(_info(fetch, "homeassistant", oldest).get("requires_python"))
        if isinstance(oldest, str) and oldest != newest
        else ""
    )
    return found


def main(arguments: list[str]) -> None:
    """Print what `arguments` asks for."""
    match arguments:
        case [root]:
            for name, version in pythons(Path(root), _pypi).items():
                print(f"{name}={version}")
        case _:
            sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
