import httpx
import pytest
from faker import Faker

from oidc_provider_mock._client_lib import AuthorizationServerError, OidcClient

from .conftest import fake_client

faker = Faker()


def test_openid_scope_required(oidc_server: str):
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


def test_email_claim_excluded_without_scope(oidc_server: str):
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
    assert token_data.scope == "openid"
    assert "email" not in token_data.claims


def test_scope_capped_to_client_registration(oidc_server: str):
    state = faker.password()

    client = OidcClient.register(
        oidc_server,
        scope="openid other",
        redirect_uri=faker.uri(schemes=["https"]),
    )

    response = httpx.post(
        client.authorization_url(state=state, scope="openid other notallowed"),
        data={"sub": faker.email()},
    )

    token_data = client.fetch_token(response.headers["location"], state)
    assert token_data.scope == "openid other"
