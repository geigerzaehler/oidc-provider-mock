from http import HTTPStatus

import httpx
import pytest
from authlib.integrations.base_client import OAuthError
from faker import Faker

from oidc_provider_mock._client_lib import OidcClient

from .conftest import fake_client, use_provider_config

faker = Faker()


@use_provider_config(require_client_registration=True)
def test_unregistered_client_rejected(oidc_server: str):
    state = faker.password()

    client = fake_client(oidc_server)

    response = httpx.post(
        client.authorization_url(state=state),
        data={"sub": faker.email()},
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert "Error: invalid_client" in response.text
    assert "The client does not exist on this server" in response.text


def test_wrong_secret_rejected(oidc_server: str):
    state = faker.password()
    redirect_uri = faker.uri(schemes=["https"])

    client = OidcClient.register(oidc_server, redirect_uri=redirect_uri)

    # Create a second client with the same ID but different secret
    client = OidcClient(
        issuer=oidc_server,
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


def test_unregistered_auth_method_rejected(oidc_server: str):
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
        issuer=oidc_server,
    )
    auth_url = client.authorization_url(state=state)
    response = httpx.post(auth_url, data={"sub": faker.email()})
    with pytest.raises(OAuthError, match="invalid_client: "):
        client.fetch_token(response.headers["location"], state=state)
