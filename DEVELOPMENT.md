# Development Guide

## Publishing a release

1. `git fetch`
1. `git checkout main`
1. Set the version to `X.Y.Z` in `pyproject.toml`
1. `uv lock`
1. `git commit -a --message "release: X.Y.Z"`
1. `git tag vX.Y.Z`
1. `git push origin tag vX.Y.Z`
1. `git push main`

Github Actions will automatically publish a new release to PyPI.
