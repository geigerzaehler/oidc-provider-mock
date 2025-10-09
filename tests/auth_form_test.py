import re
from http import HTTPStatus
from urllib.parse import urlencode

import flask.testing
import httpx
import pytest
from faker import Faker
from playwright.sync_api import Page, expect

from oidc_provider_mock._client_lib import OidcClient
from oidc_provider_mock._storage import User

from .conftest import use_provider_config

faker = Faker()


@pytest.mark.parametrize("method", ["GET", "POST"])
@use_provider_config(require_client_registration=True)
def test_invalid_client(client: flask.testing.FlaskClient, method: str):
    """
    Respond with 400 and error description when:

    * client_id query parameter is missing
    * client unknown
    * redirect_uri does not match the URI that was registered
    """

    query = urlencode({
        "redirect_uri": "foo",
        "response_type": "code",
    })
    response = client.open(f"/oauth2/authorize?{query}", method=method)
    assert response.status_code == 400
    assert "Error: invalid_client" in response.text
    assert "Missing &#39;client_id&#39; parameter" in response.text

    query = urlencode({
        "client_id": "UNKNOWN",
        "redirect_uri": "foo",
        "response_type": "code",
    })
    response = client.open(f"/oauth2/authorize?{query}", method=method)
    assert response.status_code == 400
    assert "Error: invalid_client" in response.text
    assert "The client does not exist on this server" in response.text

    redirect_uris = [faker.uri(schemes=["https"])]
    response = client.post(
        "/oauth2/clients",
        json={
            "redirect_uris": redirect_uris,
        },
    )
    assert response.status_code == HTTPStatus.CREATED
    oidc_client = response.json
    assert oidc_client

    query = urlencode({
        "client_id": oidc_client["client_id"],
        "redirect_uri": "foo",
        "response_type": "code",
    })
    response = client.open(f"/oauth2/authorize?{query}", method=method)
    assert response.status_code == 400
    assert "Error: invalid_client" in response.text
    assert "Redirect URI foo is not supported by client." in response.text


@pytest.mark.parametrize("method", ["GET", "POST"])
def test_missing_redirect_uri(client: flask.testing.FlaskClient, method: str):
    query = urlencode({
        "client_id": str(faker.uuid4()),
        "response_type": "code",
    })
    response = client.open(f"/oauth2/authorize?{query}", method=method)
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json
    assert response.json["error"] == "invalid_request"
    assert re.match(
        r"Missing ['\"]redirect_uri['\"] in request\.",
        response.json["error_description"],
    )


def test_missing_sub_parameter(client: flask.testing.FlaskClient):
    query = urlencode({
        "client_id": str(faker.uuid4()),
        "redirect_uri": faker.uri(schemes=["https"]),
        "response_type": "code",
    })
    response = client.post(f"/oauth2/authorize?{query}")
    assert "The field is missing" in response.text


def test_authorized_users_buttons_appear(oidc_server: str, page: Page):
    """Test that authorizing 3 users creates buttons on the auth page"""

    client = OidcClient(
        id=str(faker.uuid4()),
        secret=faker.password(),
        redirect_uri=faker.uri(schemes=["https"]),
        issuer=oidc_server,
    )

    subject0 = faker.email()
    subject1 = faker.email()

    for sub in [subject0, subject1, subject0]:
        httpx.post(
            client.authorization_url(state=faker.password()),
            data={"sub": sub},
        )

    page.goto(f"{oidc_server}/oidc/login")
    page.get_by_role("button", name="Start").click()

    expect(
        page.get_by_role("heading", name="Authenticate previous users")
    ).to_be_visible()

    auth_buttons = page.get_by_role(
        "form", name="Authenticate previous users"
    ).get_by_role("button")

    expect(auth_buttons.nth(0)).to_have_accessible_name(subject0)
    expect(auth_buttons.nth(1)).to_have_accessible_name(subject1)

    auth_buttons.nth(0).click()
    expect(page.locator("body")).to_contain_text(f"You’re logged in as {subject0}")


@use_provider_config(
    user_claims=(
        User(sub="alice", claims={"email": "alice@example.com", "name": "Alice"}),
        User(sub="bob", claims={"email": "bob@example.com"}),
    )
)
def test_predefined_users_button(oidc_server: str, page: Page):
    """Test that predefined users appear as buttons on the auth page"""

    OidcClient(
        id=str(faker.uuid4()),
        secret=faker.password(),
        redirect_uri=faker.uri(schemes=["https"]),
        issuer=oidc_server,
    )

    page.goto(f"{oidc_server}/oidc/login")
    page.get_by_role("button", name="Start").click()

    expect(
        page.get_by_role("heading", name="Authenticate predefined users")
    ).to_be_visible()

    predefined_buttons = page.get_by_role(
        "form", name="Authenticate predefined users"
    ).get_by_role("button")

    expect(predefined_buttons.nth(0)).to_have_accessible_name("alice")
    expect(predefined_buttons.nth(1)).to_have_accessible_name("bob")

    predefined_buttons.nth(0).click()
    expect(page.locator("body")).to_contain_text("You’re logged in as alice")

    page.goto(f"{oidc_server}/oidc/login")
    page.get_by_role("button", name="Start").click()
    expect(
        page.get_by_role("heading", name="Authenticate previous users")
    ).not_to_be_visible()
