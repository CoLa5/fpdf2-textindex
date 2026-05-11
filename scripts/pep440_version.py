"""Check PEP440 version."""

# ruff: noqa: D103

import sys

from packaging.version import InvalidVersion
from packaging.version import Version


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: validate_version.py <version>")
        return 2
    tag = sys.argv[1]

    try:
        Version(tag)
    except InvalidVersion:
        print(f"Invalid PEP 440 version: {tag:s}")
        return 1
    print(f"Valid PEP 440 version: {tag:s}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
