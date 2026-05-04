"""Tests the authorization code flow via direct HTTP requests."""

import re
from typing import Any

import httpx
import pytest
from faker import Faker

from oidc_provider_mock._client_lib import AuthorizationError, OidcClient
from oidc_provider_mock._storage import User

from .conftest import fake_client, use_provider_config

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


def test_user_endpoint_claims_in_tokens(oidc_server: str):
    """Authenticate with additional claims in ID token and user info"""

    subject = faker.email()
    state = faker.password()

    httpx.put(
        f"{oidc_server}/users/{subject}",
        json={"custom": "CLAIM"},
    ).raise_for_status()

    client = fake_client(issuer=oidc_server)

    response = httpx.post(
        client.authorization_url(state=state),
        data={"sub": subject},
    )

    token_data = client.fetch_token(response.headers["location"], state=state)
    assert token_data.claims["sub"] == subject
    assert token_data.claims["custom"] == "CLAIM"

    userinfo = client.fetch_userinfo(token=token_data.access_token)
    assert userinfo["sub"] == subject
    assert userinfo["custom"] == "CLAIM"


@use_provider_config(
    user_claims=(User(sub="alice", claims={"custom": "CLAIM"}),),
)
def test_preconfigured_claims_in_tokens(oidc_server: str):
    """Authenticate with claims configured statically"""

    state = faker.password()

    client = fake_client(issuer=oidc_server)

    response = httpx.post(
        client.authorization_url(state=state),
        data={"sub": "alice"},
    )

    token_data = client.fetch_token(response.headers["location"], state=state)
    assert token_data.claims["sub"] == "alice"
    assert token_data.claims["custom"] == "CLAIM"

    userinfo = client.fetch_userinfo(token=token_data.access_token)
    assert userinfo["sub"] == "alice"
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
    assert token_data.scope == "openid profile email address phone"

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


@use_provider_config(require_nonce=True)
def test_nonce_required_error(oidc_server: str):
    state = faker.password()

    client = fake_client(oidc_server)
    auth_url = client.authorization_url(state=state)
    token_data = httpx.post(auth_url, data={"sub": faker.email()})
    with pytest.raises(
        AuthorizationError,
        match=re.compile(
            r"Authorization failed: invalid_request: Missing ['\"]nonce['\"] in request"
        ),
    ):
        client.fetch_token(token_data.headers["location"], state=state)

    nonce = faker.password()
    auth_url = client.authorization_url(state=state, nonce=nonce)
    token_data = httpx.post(auth_url, data={"sub": faker.email()})
    token_data = client.fetch_token(token_data.headers["location"], state=state)
    assert token_data.claims["nonce"] == nonce
