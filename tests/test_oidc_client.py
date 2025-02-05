# pyright: reportUnknownMemberType=none, reportUnknownVariableType=none, reportUnknownArgumentType=none
from dataclasses import dataclass
from urllib.parse import parse_qsl, urljoin, urlparse

import authlib.jose
import authlib.oauth2.rfc6749
import authlib.oidc.core
import httpx
import pydantic
from authlib.integrations.httpx_client import OAuth2Client
from faker import Faker

faker = Faker()


@dataclass(kw_only=True, frozen=True)
class TokenData:
    access_token: str
    expires_in: int
    refresh_token: str | None
    claims: dict[str, object]


@dataclass(kw_only=True, frozen=True)
class RefreshTokenData:
    access_token: str
    expires_in: int
    refresh_token: str | None
    claims: dict[str, object] | None


class OidcClient:
    DEFAULT_SCOPE = "openid email"

    _authlib_client: OAuth2Client

    def __init__(
        self,
        issuer: str,
        *,
        id: str | None = None,
        redirect_uri: str | None = None,
        auth_method: str = "client_secret_basic",
        scope: str = DEFAULT_SCOPE,
        secret: str | None = None,
    ) -> None:
        if redirect_uri is None:
            redirect_uri = faker.uri(schemes=["https"])

        self._id = id or str(faker.uuid4())
        self._secret = secret or faker.password()
        self._scope = scope

        config = self.get_authorization_server_metadata(issuer)

        self._jwks = authlib.jose.JsonWebKey.import_key_set(
            httpx.get(config["jwks_uri"]).json()
        )

        self._provider_url = issuer

        self._token_endpoint_url = config["token_endpoint"]
        self._userinfo_enpoint_url = config["userinfo_endpoint"]
        self._authorization_endpoint_url = config["authorization_endpoint"]

        self._auth_method = auth_method

        self._authlib_client = OAuth2Client(
            client_id=self._id,
            client_secret=self._secret,
            token_endpoint_auth_method=auth_method,
            redirect_uri=redirect_uri,
        )

    @classmethod
    def get_authorization_server_metadata(cls, provider_url: str):
        # TODO: validate response schema
        return (
            httpx.get(
                urljoin(provider_url, ".well-known/openid-configuration"),
                follow_redirects=True,
            )
            .raise_for_status()
            .json()
        )

    @classmethod
    def register(
        cls,
        provider_url: str,
        redirect_uri: str | None = None,
        scope: str = DEFAULT_SCOPE,
        auth_method: str = "client_secret_basic",
    ):
        """Register a client with the OpenID provider and instantiate it."""

        config = cls.get_authorization_server_metadata(provider_url)

        if redirect_uri is None:
            redirect_uri = faker.uri(schemes=["https"])

        # TODO: handle
        if endpoint := config.get("registration_endpoint"):
            content = (
                httpx.post(
                    endpoint,
                    json={
                        "redirect_uris": [redirect_uri],
                        "token_endpoint_auth_method": auth_method,
                        "scope": scope,
                    },
                )
                .raise_for_status()
                .json()
            )

        else:
            # TODO: Dedicated error class
            raise Exception(
                "Authorization server does not advertise registration endpoint"
            )

        return cls(
            provider_url,
            id=content["client_id"],
            redirect_uri=redirect_uri,
            scope=scope,
            secret=content["client_secret"],
        )

    @property
    def secret(self) -> str:
        return self._secret

    @property
    def id(self) -> str:
        return self._id

    def authorization_url(
        self,
        *,
        state: str,
        scope: str | None = None,
        response_type: str = "code",
        nonce: str | None = None,
    ) -> str:
        if scope is None:
            scope = self._scope
        extra = {
            "scope": scope,
            "response_type": response_type,
        }
        if nonce is not None:
            extra["nonce"] = nonce

        url, _state = self._authlib_client.create_authorization_url(
            self._authorization_endpoint_url,
            state,
            code_verifier=None,
            **extra,
        )
        return url

    def fetch_token(
        self,
        auth_response_location: str,
        state: str,
    ) -> TokenData:
        """Parse authorization endpoint response embedded in the redirect location
        and fetches the token.


        :raises AuthorizationError: if authorization was unsuccessful.
        """
        query = urlparse(auth_response_location).query
        params = dict(parse_qsl(query))

        if error := params.get("error"):
            raise AuthorizationError(error, params.get("error_description"))

        if "state" not in params:
            raise AuthorizationServerError(
                "state parameter missing from authorization response"
            )
        if params["state"] != state:
            raise AuthorizationServerError(
                "state parameter in authorization_response does not match expected value"
            )

        # TODO: wrap authlib_integrations.base_client.OAuthError
        authlib_token = self._authlib_client.fetch_token(
            self._token_endpoint_url,
            state=state,
            authorization_response=auth_response_location,
        )

        try:
            response = _TokenResponse.model_validate(authlib_token)
        except pydantic.ValidationError as e:
            # TODO: include validation error information
            raise AuthorizationServerError("invalid token endpoint response") from e

        if response.id_token is None:
            raise AuthorizationServerError(
                "missing id_token from token endpoint response"
            )

        claims = authlib.jose.jwt.decode(
            response.id_token,
            self._jwks,
            claims_cls=authlib.oidc.core.CodeIDToken,
            claims_params={"iss": self._provider_url},
        )
        claims.validate()

        return TokenData(
            access_token=response.access_token,
            expires_in=response.expires_in,
            claims=dict(claims),
            refresh_token=response.refresh_token,
        )

    def fetch_userinfo(self, token: str):
        # TODO: validate response schema
        return (
            httpx.get(
                self._userinfo_enpoint_url, headers={"authorization": f"bearer {token}"}
            )
            .raise_for_status()
            .json()
        )

    def refresh_token(self, refresh_token: str) -> RefreshTokenData:
        authlib_token = self._authlib_client.fetch_token(
            self._token_endpoint_url,
            refresh_token=refresh_token,
            grant_type="refresh_token",
        )

        try:
            response = _TokenResponse.model_validate(authlib_token)
        except pydantic.ValidationError as e:
            # TODO: include validation error information
            raise AuthorizationServerError("invalid token endpoint response") from e

        if response.id_token:
            claims = authlib.jose.jwt.decode(
                response.id_token,
                self._jwks,
                claims_cls=authlib.oidc.core.CodeIDToken,
                claims_params={"iss": self._provider_url},
            )
            claims.validate()
            claims = dict(claims)
        else:
            claims = None

        return RefreshTokenData(
            access_token=response.access_token,
            expires_in=response.expires_in,
            claims=claims,
            refresh_token=response.refresh_token,
        )


class AuthorizationServerError(Exception):
    """The authorization server sent an invalid response.

    For example, the server did not return an access token from the token endpoint
    response.
    """

    def __init__(self, msg: str) -> None:
        super().__init__(msg)


class AuthorizationError(Exception):
    """The authorization server responded with an error to the authorization request.

    See [OAuth2.0 Authorization Error
    Response](https://www.rfc-editor.org/rfc/rfc6749.html#section-4.1.2.1).
    """

    def __init__(self, error: str, description: str | None = None) -> None:
        self.error = error
        self.description = description

        msg = f"Authorization failed: {error}"
        if description:
            msg = f"{msg}: {description}"

        super().__init__(msg)


class _TokenResponse(pydantic.BaseModel):
    """Response body for successful requests to the token endpoint.

    See https://www.rfc-editor.org/rfc/rfc6749.html#section-5 and
    https://openid.net/specs/openid-connect-core-1_0.html#TokenResponse
    """

    access_token: str
    expires_in: int
    refresh_token: str | None = None
    id_token: str | None = None
