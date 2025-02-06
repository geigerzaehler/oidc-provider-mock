"""Tests authentication flow only using the POST requests to the authorization
endopint.
"""

from datetime import timedelta
from http import HTTPStatus
from typing import Any

import httpx
import pytest
from authlib.integrations.base_client import OAuthError
from faker import Faker

from oidc_provider_mock._client_lib import (
    AuthorizationError,
    AuthorizationServerError,
    OidcClient,
)

from .conftest import use_provider_config

faker = Faker()


@use_provider_config(require_client_registration=True)
def test_auth_success(oidc_server: str):
    """Authorization Code flow success with client registration"""

    subject = faker.email()
    state = faker.password()
    nonce = faker.password()
    redirect_uri = faker.uri(schemes=["https"])

    client = OidcClient.register(oidc_server, redirect_uri=redirect_uri)

    response = httpx.post(
        client.authorization_url(state=state, nonce=nonce),
        data={"sub": subject},
    )
    assert response.status_code == 302
    location = response.headers["location"]
    assert location.startswith(redirect_uri)
    token_data = client.fetch_token(location, state=state)

    assert token_data.claims["sub"] == subject
    assert token_data.claims["email"] == subject
    assert token_data.claims["nonce"] == nonce

    userinfo = client.fetch_userinfo(token=token_data.access_token)
    assert userinfo["sub"] == subject


def test_custom_claims(oidc_server: str):
    """Authenticate with additional claims in ID token and user info"""

    subject = faker.email()
    state = faker.password()

    httpx.put(
        f"{oidc_server}/users/{subject}",
        json={"custom": "CLAIM"},
    ).raise_for_status()

    client = fake_client(issuer=oidc_server)

    token_data = httpx.post(
        client.authorization_url(state=state),
        data={"sub": subject},
    )

    token_data = client.fetch_token(token_data.headers["location"], state=state)
    assert token_data.claims["sub"] == subject
    assert token_data.claims["custom"] == "CLAIM"

    userinfo = client.fetch_userinfo(token=token_data.access_token)
    assert userinfo["sub"] == subject
    assert userinfo["custom"] == "CLAIM"


def test_include_all_claims(oidc_server: str):
    subject = faker.email()
    state = faker.password()
    claims: dict[str, Any] = {
        # profile scope
        "name": faker.name(),
        "website": faker.uri(),
        # email scope
        "email": faker.email(),
        # address scope
        "address": {
            "formatted": faker.address(),
        },
        # phone scope
        "phone": faker.phone_number(),
    }

    httpx.put(f"{oidc_server}/users/{subject}", json=claims).raise_for_status()

    client = fake_client(
        issuer=oidc_server,
        scope="openid profile email address phone",
    )

    response = httpx.post(
        client.authorization_url(state=state),
        data={"sub": subject},
    )

    token_data = client.fetch_token(response.headers["location"], state=state)
    assert token_data.claims["sub"] == subject
    assert token_data.claims["name"] == claims["name"]
    assert token_data.claims["website"] == claims["website"]
    assert token_data.claims["email"] == claims["email"]
    assert token_data.claims["address"]["formatted"] == claims["address"]["formatted"]  # type: ignore
    assert token_data.claims["phone"] == claims["phone"]

    user_info = client.fetch_userinfo(token=token_data.access_token)
    assert user_info["sub"] == subject
    assert user_info["name"] == claims["name"]
    assert user_info["website"] == claims["website"]
    assert user_info["email"] == claims["email"]
    assert user_info["address"]["formatted"] == claims["address"]["formatted"]
    assert user_info["phone"] == claims["phone"]


def test_auth_denied(oidc_server: str):
    state = faker.password()

    client = fake_client(oidc_server)

    response = httpx.post(
        client.authorization_url(state=faker.password()),
        data={"action": "deny"},
    )

    with pytest.raises(AuthorizationError, match=r"access_denied"):
        client.fetch_token(response.headers["location"], state=state)


@use_provider_config(require_client_registration=True)
def test_client_not_registered(oidc_server: str):
    state = faker.password()

    client = fake_client(oidc_server)

    response = httpx.post(
        client.authorization_url(state=state),
        data={"sub": faker.email()},
    )

    # TODO: Render an HTML error
    # auth error response redirect.
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert "Error: invalid_client" in response.text
    assert "Invalid client_id query parameter" in response.text


def test_wrong_client_secret(oidc_server: str):
    state = faker.password()
    redirect_uri = faker.uri(schemes=["https"])

    client = OidcClient.register(oidc_server, redirect_uri=redirect_uri)

    # Create a second client with the same ID but different secret
    client = OidcClient(
        provider_url=oidc_server,
        id=client.id,
        secret="foobar",
        redirect_uri=redirect_uri,
    )

    response = httpx.post(
        client.authorization_url(state=state),
        data={"sub": faker.email()},
    )

    with pytest.raises(OAuthError, match="invalid_client: "):
        client.fetch_token(response.headers["location"], state=state)


@pytest.mark.parametrize(
    "auth_method",
    [
        "client_secret_basic",
        "client_secret_post",
    ],
)
def test_client_auth_methods(oidc_server: str, auth_method: str):
    subject = faker.email()
    state = faker.password()

    client = fake_client(oidc_server, auth_method=auth_method)
    auth_url = client.authorization_url(state=state)
    response = httpx.post(auth_url, data={"sub": subject})

    token_data = client.fetch_token(response.headers["location"], state)
    assert token_data.claims["sub"] == subject

    userinfo = client.fetch_userinfo(token=token_data.access_token)
    assert userinfo["sub"] == subject


def test_auth_methods_not_supported_for_client(oidc_server: str):
    state = faker.password()

    redirect_uri = faker.uri()
    client = OidcClient.register(
        oidc_server, redirect_uri=redirect_uri, auth_method="client_secret_basic"
    )
    client = OidcClient(
        id=client.id,
        redirect_uri=redirect_uri,
        auth_method="client_secret_post",
        secret=client.secret,
        provider_url=oidc_server,
    )
    auth_url = client.authorization_url(state=state)
    response = httpx.post(auth_url, data={"sub": faker.email()})
    with pytest.raises(OAuthError, match="invalid_client: "):
        client.fetch_token(response.headers["location"], state=state)


@use_provider_config(require_nonce=True)
def test_nonce_required_error(oidc_server: str):
    state = faker.password()

    client = fake_client(oidc_server)
    auth_url = client.authorization_url(state=state)
    token_data = httpx.post(auth_url, data={"sub": faker.email()})
    with pytest.raises(
        AuthorizationError,
        match='Authorization failed: invalid_request: Missing "nonce" in request',
    ):
        client.fetch_token(token_data.headers["location"], state=state)

    nonce = faker.password()
    auth_url = client.authorization_url(state=state, nonce=nonce)
    token_data = httpx.post(auth_url, data={"sub": faker.email()})
    token_data = client.fetch_token(token_data.headers["location"], state=state)
    assert token_data.claims["nonce"] == nonce


def test_no_openid_scope(oidc_server: str):
    state = faker.password()

    client = fake_client(oidc_server, scope="foo bar")

    response = httpx.post(
        client.authorization_url(state=state),
        data={"sub": faker.email()},
    )

    with pytest.raises(
        AuthorizationServerError, match="missing id_token from token endpoint response"
    ):
        client.fetch_token(response.headers["location"], state)


def test_no_email_scope(oidc_server: str):
    state = faker.password()

    client = OidcClient.register(
        oidc_server,
        scope="openid",
        redirect_uri=faker.uri(schemes=["https"]),
    )

    response = httpx.post(
        client.authorization_url(state=state),
        data={"sub": faker.email()},
    )

    token_data = client.fetch_token(response.headers["location"], state)
    assert "email" not in token_data.claims


@use_provider_config(access_token_max_age=timedelta(minutes=111))
def test_token_expiry(oidc_server: str):
    state = faker.password()

    client = OidcClient.register(oidc_server, redirect_uri=faker.uri(schemes=["https"]))

    response = httpx.post(
        client.authorization_url(state=state),
        data={"sub": faker.email()},
    )
    assert response.status_code == 302
    token_data = client.fetch_token(response.headers["location"], state=state)

    assert token_data.claims["exp"] - token_data.claims["iat"] == 111 * 60  # type: ignore
    assert token_data.expires_in == 111 * 60


@use_provider_config(issue_refresh_token=False)
def test_no_refresh_token(oidc_server: str):
    state = faker.password()

    client = OidcClient.register(oidc_server, redirect_uri=faker.uri(schemes=["https"]))

    response = httpx.post(
        client.authorization_url(state=state),
        data={"sub": faker.email()},
    )
    assert response.status_code == 302
    token_data = client.fetch_token(response.headers["location"], state=state)

    assert token_data.refresh_token is None


def test_refresh_token(oidc_server: str):
    state = faker.password()

    client = OidcClient.register(oidc_server, redirect_uri=faker.uri(schemes=["https"]))

    response = httpx.post(
        client.authorization_url(state=state),
        data={"sub": faker.email()},
    )

    token_data = client.fetch_token(response.headers["location"], state=state)

    assert token_data.refresh_token is not None
    refresh_token_data = client.refresh_token(refresh_token=token_data.refresh_token)

    with pytest.raises(httpx.HTTPStatusError) as e:
        client.fetch_userinfo(token=token_data.access_token)

    assert e.value.response.json()["error"] == "access_denied"

    client.fetch_userinfo(token=refresh_token_data.access_token)


def fake_client(
    issuer: str,
    *,
    scope: str = OidcClient.DEFAULT_SCOPE,
    auth_method: str = OidcClient.DEFAULT_AUTH_METHOD,
):
    return OidcClient(
        id=str(faker.uuid4()),
        secret=faker.password(),
        redirect_uri=faker.uri(schemes=["https"]),
        provider_url=issuer,
        scope=scope,
        auth_method=auth_method,
    )
