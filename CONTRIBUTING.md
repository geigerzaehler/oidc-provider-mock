# Contributing

Contributions and suggestions are very welcome. You can find the code on
[Github](https://github.com/geigerzaehler/oidc-provider-mock).

The project uses [uv](https://docs.astral.sh/uv/getting-started/installation/) for dependency management.

[Ruff](https://docs.astral.sh/ruff/) is used for formatting and linting.
[Pyright](https://microsoft.github.io/pyright/) is used for type-checking.

```bash
uv run ruff format --check
uv run ruff check
uv run pyright --warnings
```

The tests use [Playwright](https://playwright.dev/) to run browser-based tests.

```bash
uv run playwright install chromium
uv run pytest
```

The documentation is build using [Sphinx](https://www.sphinx-doc.org).

```bash
uv run sphinx-build --fail-on-warning docs docs/dist
```

To preview and watch the documentation run

```bash
uvr sphinx-autobuild docs docs/dist -a --watch src --watch docs
```

## Releases

To prepare a release:

1. Update the version in `./pyproject.toml`
1. Run `uv lock`
1. Commit the changes with the message `release: vX.Y.Z`
1. Tag the commit with `vX.Y.Z` and push the tag: `git tag vX.Y.Z && git push
origin tag vX.Y.Z`

The publish workflow will build and publish the release to PyPI.
