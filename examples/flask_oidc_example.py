# pyright: reportUnknownMemberType=none
"""Test OIDC login of a Flask app using
[Flask-OIDC](https://flask-oidc.readthedocs.io/en/stable/).
"""

import logging
from pathlib import Path
from urllib.parse import quote

import flask
import flask.testing
import httpx
import pytest
from flask_oidc import OpenIDConnect
from playwright.sync_api import Page, expect
from pytest_flask.live_server import LiveServer

import oidc_provider_mock


def build_app(oidc_provider_url: str):
    app = flask.Flask(__name__)
    app.config.update({
        "OIDC_CLIENT_SECRETS": Path(__file__).parent / "flask_oidc_client_secrets.json",
        "OIDC_INTROSPECTION_AUTH_METHOD": "client_secret_basic",
        "OIDC_SCOPES": "openid profile email",
        "SECRET_KEY": "some secret",
        "SERVER_NAME": "localhost",  # See https://github.com/pytest-dev/pytest-flask/issues/175
    })

    @app.route("/")
    def index():
        user = flask.g.oidc_user
        if user.logged_in:
            return f"Welcome {user.profile['name']} ({user.email})"
        else:
            return "Not logged in"

    app.config["OIDC_SERVER_METADATA_URL"] = (
        f"{oidc_provider_url}/.well-known/openid-configuration"
    )
    OpenIDConnect(app)

    return app


@pytest.fixture
def app(oidc_server: str):
    logging.getLogger("oidc_provider_mock").setLevel(logging.DEBUG)
    app = build_app(oidc_server)
    return app


# SNIPPET flask_test_login


@pytest.fixture
def oidc_server():
    with oidc_provider_mock.run_server_in_thread() as server:
        yield f"http://localhost:{server.server_port}"


def test_auth_code_login(client: flask.testing.FlaskClient, oidc_server: str):
    # Add OIDC claims for the user we want to authenticate
    response = httpx.put(
        f"{oidc_server}/users/{quote('alice@example.com')}",
        json={"email": "alice@example.com", "name": "Alice", "custom": ["foo", "bar"]},
    )
    assert response.status_code == 204

    # Start login on the client and get the authorization URL
    response = client.get("/login")
    assert response.location

    # Authorize the client by POSTing to the authorization URL.
    response = httpx.post(response.location, data={"sub": "alice@example.com"})

    # Go back to the client with the authorization code
    assert response.has_redirect_location
    response = client.get(response.headers["location"], follow_redirects=True)

    # Check that we have been authenticated
    assert response.text == "Welcome Alice (alice@example.com)"


# SNIPPET END

# SNIPPET flask_test_login_playwright


def test_auth_code_login_playwright(
    live_server: LiveServer, oidc_server: str, page: Page
):
    # Let the OIDC provider know about the user’s email and name
    response = httpx.put(
        f"{oidc_server}/users/{quote('alice@example.com')}",
        json={"email": "alice@example.com", "name": "Alice"},
    )
    assert response.status_code == 204

    # Start login and be redirected to the provider
    page.goto(live_server.url("/login"))

    # Authorize with the provider
    page.get_by_placeholder("sub").fill("alice@example.com")
    page.get_by_role("button", name="Authorize").click()

    # Verify that we’re logged in
    expect(page.locator("body")).to_contain_text("Welcome Alice (alice@example.com)")


# SNIPPET END


def test_auth_denied_playwright(live_server: LiveServer, oidc_server: str, page: Page):
    """Test user denying authorization"""

    # Start login and be redirected to the provider
    page.goto(live_server.url("/login"))

    # Deny authorization
    page.get_by_role("button", name="Deny").click()

    # Verify that we’re shown an error message
    expect(page.get_by_role("heading")).to_have_text("Unauthorized")
    expect(page.locator("body")).to_contain_text(
        "access_denied: The resource owner or authorization server denied the request"
    )
