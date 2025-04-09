#!/usr/bin/env -S uv run

import os
import subprocess
import sys
from pathlib import Path

import toml


class UsageError(Exception):
    def __init__(self, msg: str) -> None:
        super().__init__(msg)
        self.msg = msg


def main():
    """Check that the git ref can be published.

    1. Check that the tag name matches the version in `pyproject.toml`
    2. Check that the commit message is `release: vX.Y.Z`
    """
    pyproject_data = toml.load(Path("pyproject.toml"))
    version = pyproject_data["project"]["version"]
    ref_prefix = "refs/tags/v"
    github_ref = os.getenv("GITHUB_REF")
    if not github_ref:
        raise UsageError("GITHUB_REF environment variable not set")
    if not github_ref.startswith(ref_prefix):
        raise UsageError(f"GITHUB_REF environment does not start with {ref_prefix}")

    tag_version = github_ref.removeprefix(ref_prefix)

    if tag_version != version:
        raise UsageError(
            f"Tagged version `{tag_version}` does not match version `{version}` from pyproject.toml "
        )

    commit_subject = subprocess.run(
        ["git", "log", "-1", "--pretty=%s"],
        stdout=subprocess.PIPE,
        text=True,
        check=True,
    ).stdout.strip()

    expected_subject = f"release: v{version}"
    if commit_subject != expected_subject:
        raise UsageError(
            "Invalid commit message for release publish.\n"
            f"Expected subject `{expected_subject}`, got `{commit_subject}`"
        )


if __name__ == "__main__":
    try:
        main()
    except UsageError as e:
        print(f"ERROR: {e.msg}")  # noqa: T201
        sys.exit(1)
