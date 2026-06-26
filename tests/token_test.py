from datetime import timedelta

import flask.testing
import httpx
import joserfc.jws
import pytest
from authlib.integrations.base_client import OAuthError
from faker import Faker
from freezegun import freeze_time

from oidc_provider_mock._client_lib import OidcClient, TokenData

from .conftest import fake_client, use_provider_config

faker = Faker()


@use_provider_config(access_token_max_age=timedelta(minutes=111))
def test_configured_token_max_age(oidc_server: str):
    client = OidcClient.register(oidc_server, redirect_uri=faker.uri(schemes=["https"]))

    token_data = _authorize_and_fetch_token(client)

    assert token_data.claims["exp"] - token_data.claims["iat"] == 111 * 60  # type: ignore
    assert token_data.expires_in == 111 * 60


@use_provider_config(issue_refresh_token=False)
def test_refresh_token_not_issued_when_disabled(oidc_server: str):
    client = fake_client(oidc_server)

    token_data = _authorize_and_fetch_token(client)

    assert token_data.refresh_token is None


def test_refresh_token_rotates_access_token(oidc_server: str):
    client = fake_client(oidc_server)

    token_data = _authorize_and_fetch_token(client)

    assert token_data.refresh_token is not None
    refresh_token_data = client.refresh_token(refresh_token=token_data.refresh_token)

    # Using a refresh token revokes the old access token
    with pytest.raises(httpx.HTTPStatusError) as e:
        client.fetch_userinfo(token=token_data.access_token)
    assert e.value.response.json()["error"] == "access_denied"

    client.fetch_userinfo(token=refresh_token_data.access_token)


@use_provider_config(access_token_max_age=timedelta(minutes=2))
def test_refresh_token_respects_configured_token_max_age(oidc_server: str):
    client = fake_client(oidc_server)

    token_data = _authorize_and_fetch_token(client)
    assert token_data.expires_in == 2 * 60

    assert token_data.refresh_token is not None
    refresh_token_data = client.refresh_token(refresh_token=token_data.refresh_token)

    assert refresh_token_data.expires_in == 2 * 60
    assert refresh_token_data.claims["exp"] - refresh_token_data.claims["iat"] == 2 * 60  # type: ignore


def test_refresh_token_issues_id_token(oidc_server: str):
    client = fake_client(oidc_server)
    email = faker.email()

    token_data = _authorize_and_fetch_token(client, sub=email)

    assert token_data.refresh_token is not None
    refresh_token_data = client.refresh_token(refresh_token=token_data.refresh_token)

    assert refresh_token_data.claims is not None
    assert refresh_token_data.claims["sub"] == email


def test_revoke_tokens(oidc_server: str):
    sub = faker.email()
    client = fake_client(oidc_server)

    token_data = _authorize_and_fetch_token(client, sub=sub)

    httpx.post(f"{oidc_server}users/{sub}/revoke-tokens").raise_for_status()

    with pytest.raises(httpx.HTTPStatusError) as e:
        client.fetch_userinfo(token=token_data.access_token)
    assert e.value.response.json()["error"] == "access_denied"

    assert token_data.refresh_token is not None
    with pytest.raises(OAuthError, match="invalid_grant: invalid refresh token"):
        client.refresh_token(token_data.refresh_token)


def test_unsupported_grant_type(client: flask.testing.FlaskClient):
    response = client.post("/oauth2/token", data={"grant_type": "foo"})
    assert response.json == {"error": "unsupported_grant_type"}


@use_provider_config(access_token_max_age=timedelta(minutes=111))
def test_userinfo_expired_token(oidc_server: str):
    with freeze_time(faker.date(), tick=True) as frozen_datetime:
        client = fake_client(oidc_server)
        token_data = _authorize_and_fetch_token(client)
        frozen_datetime.tick(timedelta(minutes=112))
        with pytest.raises(httpx.HTTPStatusError) as e:
            client.fetch_userinfo(token=token_data.access_token)

        response = e.value.response.json()
        assert response["error"] == "invalid_token"


def test_id_token_header_has_kid(oidc_server: str):
    client = fake_client(oidc_server)

    _authorize_and_fetch_token(client)

    id_token = client._authlib_client.token["id_token"]  # type: ignore[index]
    assert isinstance(id_token, str)
    header = joserfc.jws.extract_compact(id_token.encode()).protected
    assert "kid" in header


def _authorize_and_fetch_token(client: OidcClient, sub: str | None = None) -> TokenData:
    state = faker.password()
    response = httpx.post(
        client.authorization_url(state=state),
        data={"sub": faker.email() if sub is None else sub},
    )
    assert response.status_code == 302
    return client.fetch_token(response.headers["location"], state=state)
