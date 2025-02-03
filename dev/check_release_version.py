#!/usr/bin/env python

import os
from pathlib import Path

import toml


def main():
    pyproject_data = toml.load(Path("pyproject.toml"))
    pyproject_version = pyproject_data["project"]["version"]  # Standard PEP 621 format
    ref_prefix = "refs/tags/v"
    github_ref = os.getenv("GITHUB_REF")
    if not github_ref:
        raise RuntimeError("GITHUB_REF environment variable not set")
    if not github_ref.startswith(ref_prefix):
        raise RuntimeError(f"GITHUB_REF environment does not start with {ref_prefix}")

    tag_version = os.getenv("GITHUB_REF", "").removeprefix("refs/tags/v")

    if tag_version != pyproject_version:
        raise RuntimeError(
            f"Tagged version `{tag_version}` does not match version `{pyproject_version}` from pyproject.toml "
        )

    print(  # noqa: T201
        f"Version check passed: Tag version {tag_version} matches pyproject.toml version."
    )


if __name__ == "__main__":
    main()
