from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, urljoin, urlparse

import httpx
import joserfc.jwk
import joserfc.jwt
import pydantic
from authlib.integrations.httpx_client import OAuth2Client


@dataclass(kw_only=True, frozen=True)
class TokenData:
    """Payload of a successful access token response.

    See https://www.rfc-editor.org/rfc/rfc6749.html#section-5.1"""

    access_token: str
    expires_in: int
    refresh_token: str | None
    claims: dict[str, object]
    scope: str | None


@dataclass(kw_only=True, frozen=True)
class RefreshTokenData:
    access_token: str
    expires_in: int
    refresh_token: str | None
    claims: dict[str, object] | None


class _OidcClaims(pydantic.BaseModel):
    """Claims defined for the OpenID JWT.

    See https://openid.net/specs/openid-connect-core-1_0.html#IDToken"""

    iss: str
    aud: str | Sequence[str]
    azp: str | None = None
    exp: int
    iat: int


class InvalidClaim(Exception):
    # Name of the invalid claim, e.g. iss, aud, etc.
    name: str

    def __init__(self, name: str, message: str) -> None:
        self.name = name
        super().__init__(message)


class OidcClient:
    DEFAULT_SCOPE = "openid email"
    DEFAULT_AUTH_METHOD = "client_secret_basic"

    _authlib_client: OAuth2Client

    def __init__(
        self,
        *,
        id: str,
        redirect_uri: str,
        secret: str,
        issuer: str,
        auth_method: str = DEFAULT_AUTH_METHOD,
        scope: str = DEFAULT_SCOPE,
    ) -> None:
        self._id = id
        self._secret = secret
        self._scope = scope
        self._issuer = issuer

        # TODO: validate response
        config = self.get_authorization_server_metadata(issuer)

        self._jwks = joserfc.jwk.KeySet.import_key_set(
            httpx.get(config["jwks_uri"]).json()
        )

        self._issuer = config["issuer"]
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
        issuer: str,
        redirect_uri: str,
        scope: str = DEFAULT_SCOPE,
        auth_method: str = "client_secret_basic",
    ):
        """Register a client with the OpenID provider and instantiate it."""

        config = cls.get_authorization_server_metadata(issuer)

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
            id=content["client_id"],
            redirect_uri=redirect_uri,
            scope=scope,
            issuer=issuer,
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

        url, _state = self._authlib_client.create_authorization_url(  # pyright: ignore[reportUnknownVariableType,reportUnknownMemberType]
            self._authorization_endpoint_url,
            state,
            code_verifier=None,
            **extra,
        )
        assert isinstance(url, str)
        return url

    def fetch_token(
        self,
        auth_response_location: str,
        state: str,
    ) -> TokenData:
        # TODO: add nonce argument and check it
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
        authlib_token = self._authlib_client.fetch_token(  # pyright: ignore[reportUnknownVariableType,reportUnknownMemberType]
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

        claims = self._decode_and_verify_id_token(response.id_token)

        return TokenData(
            access_token=response.access_token,
            expires_in=response.expires_in,
            claims=claims,
            refresh_token=response.refresh_token,
            scope=response.scope,
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
        authlib_token = self._authlib_client.fetch_token(  # pyright: ignore[reportUnknownVariableType,reportUnknownMemberType]
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
            claims = self._decode_and_verify_id_token(response.id_token)
        else:
            claims = None

        return RefreshTokenData(
            access_token=response.access_token,
            expires_in=response.expires_in,
            claims=claims,
            refresh_token=response.refresh_token,
        )

    def _decode_and_verify_id_token(self, id_token: str) -> dict[str, object]:
        # See https://openid.net/specs/openid-connect-core-1_0.html#IDTokenValidation

        # 1. decode and verify signature
        token = joserfc.jwt.decode(id_token, self._jwks)
        # TODO: wrap error
        claims = _OidcClaims.model_validate(token.claims)

        # 2. iss
        if claims.iss != self._issuer:
            raise InvalidClaim("iss", f"expected {self._issuer} got {claims.iss}")

        # 3. aud
        if isinstance(claims.aud, str):
            if claims.aud != self._id:
                raise InvalidClaim("aud", f"expected {self._id} got {claims.aud}")
        else:
            aud = set(claims.aud)
            if self._id not in aud:
                raise InvalidClaim("aud", f"client ID {self._id} not included")
            untrusted = aud - {self._id}
            if untrusted:
                raise InvalidClaim(
                    "aud", f"includes untrusted audiences {', '.join(untrusted)}"
                )

        # 4. azp extension not implemented

        # 5. azp
        if claims.azp is not None and claims.azp != self._id:
            raise InvalidClaim("azp", f"expected {self._id} got {claims.azp}")

        # 6. TLS verification skipped, we’re using the signature
        # TODO: 7. Implement alg check
        # TODO: 8. Client secret check of HMAC

        now = datetime.now(tz=timezone.utc)

        # 9. exp
        exp = datetime.fromtimestamp(claims.exp, tz=timezone.utc)
        if now > exp + timedelta(seconds=5):
            raise ValueError("exp")

        # 10. iat
        iat = datetime.fromtimestamp(claims.iat, tz=timezone.utc)
        if now < iat - timedelta(hours=1):
            raise ValueError("iat")

        # 11. TODO nonce
        # 12. acr extension not implemented

        return token.claims


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
    scope: str | None = None
