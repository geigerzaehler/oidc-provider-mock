# pyright: reportPrivateUsage=none

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import timedelta
from typing import TypeVar

import flask
import pytest
import typeguard
import werkzeug.serving
from playwright.sync_api import Page

typeguard.install_import_hook("oidc_provider_mock")
import oidc_provider_mock  # noqa: E402
import oidc_provider_mock._server  # noqa: E402
from oidc_provider_mock._app import Config  # noqa: E402


@pytest.fixture
def app():
    return oidc_provider_mock.app()


@pytest.fixture
def oidc_server(request: pytest.FixtureRequest) -> Iterator[str]:
    param = getattr(request, "param", None)
    if param:
        config = Config(param)
        app = oidc_provider_mock.app(**config)
    else:
        app = oidc_provider_mock.app()

    with run_server(app) as server:
        yield server.url()


_C = TypeVar("_C", bound=Callable[..., None])


def use_provider_config(
    *,
    require_client_registration: bool = False,
    require_nonce: bool = False,
    issue_refresh_token: bool = True,
    access_token_max_age: timedelta = timedelta(hours=1),
) -> Callable[[_C], _C]:
    """Set configuration for the app under test."""

    return pytest.mark.parametrize(
        "oidc_server",
        [
            Config(
                require_client_registration=require_client_registration,
                require_nonce=require_nonce,
                issue_refresh_token=issue_refresh_token,
                access_token_max_age=access_token_max_age,
            ),
        ],
        indirect=True,
        ids=[""],
    )


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
