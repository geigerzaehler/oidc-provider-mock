# pyright: reportPrivateUsage=none

import dataclasses
import logging
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, TypeVar, cast

import flask
import pytest
import typeguard
import werkzeug.serving
from playwright.sync_api import Page

typeguard.install_import_hook("oidc_provider_mock")
import oidc_provider_mock  # noqa: E402
import oidc_provider_mock._server  # noqa: E402
from oidc_provider_mock._app import Config  # noqa: E402
from oidc_provider_mock._storage import User  # noqa: E402


@pytest.fixture
def app(request: pytest.FixtureRequest):
    node = cast("Any", request.node)  # pyright: ignore
    marker = node.get_closest_marker("provider_config")
    if marker:
        config = marker.args[0]
        app = oidc_provider_mock.app(**{
            f.name: getattr(config, f.name) for f in dataclasses.fields(config)
        })
    else:
        app = oidc_provider_mock.app()

    # When using the `client` fixture, we include the port so that authlib does
    # not complain about insecure URLs.
    app.config["SERVER_NAME"] = "localhost:54321"
    return app


_C = TypeVar("_C", bound=Callable[..., None])


def use_provider_config(
    *,
    require_client_registration: bool = False,
    require_nonce: bool = False,
    issue_refresh_token: bool = True,
    access_token_max_age: timedelta = timedelta(hours=1),
    user_claims: Sequence[User] = (),
) -> Callable[[_C], _C]:
    """Set configuration for the app under test."""

    return pytest.mark.provider_config(
        Config(
            require_client_registration=require_client_registration,
            require_nonce=require_nonce,
            issue_refresh_token=issue_refresh_token,
            access_token_max_age=access_token_max_age,
            user_claims=user_claims,
        ),
    )


@pytest.fixture(autouse=True)
def setup_logging():
    logging.getLogger("oidc_provider_mock").setLevel(logging.DEBUG)


@pytest.fixture
def oidc_server(app: flask.Flask) -> Iterator[str]:
    with run_server(app) as server:
        yield server.url()


@pytest.fixture
def page(page: Page):
    page.set_default_navigation_timeout(3000)
    page.set_default_timeout(3000)
    return page


@dataclass
class TestServer:
    app: flask.Flask
    server: werkzeug.serving.BaseWSGIServer

    def url(self, path: str = ""):
        path = path.lstrip("/")
        return f"http://localhost:{self.server.server_port}/{path}"


@contextmanager
def run_server(app: flask.Flask) -> Iterator[TestServer]:
    with oidc_provider_mock._server._threaded_server(app, poll_interval=0.01) as server:
        app.config["SERVER_NAME"] = f"localhost:{server.server_port}"
        yield TestServer(app, server)
