#!/usr/bin/python

"""Run the repository's CI checks locally, fixing Ruff issues first."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
logging.basicConfig(level=logging.INFO, format="%(message)s")
LOGGER = logging.getLogger(__name__)


def run(*command: str) -> None:
    """Run a command from the repository root and stop on failure."""
    LOGGER.info("+ %s", " ".join(command))
    # Callers pass only fixed commands defined in main().
    subprocess.run(command, cwd=ROOT, check=True)  # noqa: S603


def main() -> int:
    """Apply lint fixes and run the checks defined by the CI workflow."""
    try:
        run("uv", "sync", "--locked", "--all-groups")

        # Apply Ruff's safe fixes and formatting before running the checks.
        run("uv", "run", "ruff", "check", "--fix", "tools/", "tests/")
        run("uv", "run", "ruff", "format", "tools/", "tests/")

        run("uv", "run", "pytest")
        run("uv", "run", "ruff", "check", "tools/", "tests/")
        run("uv", "run", "ruff", "format", "--check", "tools/", "tests/")
        run("uv", "run", "pyright", "--verbose", "tools/")
        run("uv", "run", "mkdocs", "build", "--strict")
    except subprocess.CalledProcessError as error:
        return error.returncode
    except OSError as error:
        LOGGER.error("Unable to run command: %s", error)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
