from collections.abc import Collection, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import ClassVar, Literal, TypeAlias, cast

import authlib.oauth2.rfc6749
import authlib.oidc.core
import flask
import werkzeug.local
from authlib import jose
from typing_extensions import override


class ClientAllowAny:
    """Special value for client fields that skips validation of the field."""


ClientAuthMethod: TypeAlias = (
    Literal["none"] | Literal["client_secret_basic"] | Literal["client_secret_post"]
)


@dataclass(kw_only=True, frozen=True)
class Client(authlib.oauth2.rfc6749.ClientMixin):
    id: str
    secret: str | ClientAllowAny
    redirect_uris: Sequence[str] | ClientAllowAny
    allowed_scopes: Sequence[str]
    token_endpoint_auth_method: ClientAuthMethod | ClientAllowAny

    """Wrap ``Client`` to implement authlib’s client protocol."""

    RESPONSE_TYPES_SUPPORTED: ClassVar[tuple[str, ...]] = ("code",)
    GRANT_TYPES_SUPPORTED: ClassVar[tuple[str, ...]] = (
        "authorization_code",
        "refresh_token",
    )
    SCOPES_SUPPORTED: ClassVar[tuple[str, ...]] = (
        "openid",
        "profile",
        "email",
        "address",
        "phone",
    )

    @override
    def get_client_id(self):
        return self.id

    @override
    def get_default_redirect_uri(self) -> str:
        if isinstance(self.redirect_uris, ClientAllowAny):
            return "https://example.com"

        return self.redirect_uris[0]

    @override
    def get_allowed_scope(self, scope: Collection[str] | str) -> str:
        if isinstance(scope, str):
            scopes = scope.split()
        else:
            scopes = scope
        return " ".join(s for s in scopes if s in self.allowed_scopes)

    @override
    def check_redirect_uri(self, redirect_uri: str) -> bool:
        if isinstance(self.redirect_uris, ClientAllowAny):
            return True

        return redirect_uri in self.redirect_uris

    @override
    def check_client_secret(self, client_secret: str) -> bool:
        if isinstance(self.secret, ClientAllowAny):
            return True

        return client_secret == self.secret

    @override
    def check_endpoint_auth_method(self, method: str, endpoint: object):
        if isinstance(self.token_endpoint_auth_method, ClientAllowAny):
            return True

        return method == self.token_endpoint_auth_method

    @override
    def check_grant_type(self, grant_type: str):
        return grant_type in self.GRANT_TYPES_SUPPORTED

    @override
    def check_response_type(self, response_type: str):
        return response_type in self.RESPONSE_TYPES_SUPPORTED


@dataclass(kw_only=True, frozen=True)
class User:
    sub: str
    claims: dict[str, object] = field(default_factory=dict[str, object])


@dataclass(kw_only=True, frozen=True)
class AuthorizationCode(authlib.oidc.core.AuthorizationCodeMixin):
    code: str
    client_id: str
    redirect_uri: str
    user_id: str
    scope: str
    nonce: str | None

    # Implement AuthorizationCodeMixin

    @override
    def get_redirect_uri(self):
        return self.redirect_uri

    @override
    def get_scope(self):
        return self.scope

    @override
    def get_nonce(self) -> str | None:
        return self.nonce

    @override
    def get_auth_time(self) -> int | None:
        return None


@dataclass(kw_only=True, frozen=True)
class AccessToken(authlib.oauth2.rfc6749.TokenMixin):
    token: str
    user_id: str
    scope: str
    expires_at: datetime

    def get_user(self) -> User:
        user = storage.get_user(self.user_id)
        if user is None:
            raise RuntimeError(f"Missing user {self.user_id} for access toke")
        return user

    # Implement `TokenMixin`

    @override
    def check_client(self, client: Client) -> bool:
        # Required only for revocation and refresh token endpoints.
        raise NotImplementedError()

    @override
    def is_expired(self):
        return datetime.now(timezone.utc) >= self.expires_at

    @override
    def is_revoked(self):
        return False

    @override
    def get_scope(self) -> str:
        return self.scope


@dataclass(kw_only=True, frozen=True)
class RefreshToken(AccessToken):
    client_id: str
    access_token: str

    @override
    def check_client(self, client: Client) -> bool:
        return self.client_id == client.id


class Storage:
    jwk: jose.RSAKey

    _clients: dict[str, Client]
    _users: dict[str, User]
    _authorization_codes: dict[str, AuthorizationCode]
    _access_tokens: dict[str, AccessToken]
    _refresh_tokens: dict[str, RefreshToken]
    _nonces: set[str]

    def __init__(self) -> None:
        self.jwk = jose.RSAKey.generate_key(is_private=True)
        self._clients = {}
        self._users = {}
        self._authorization_codes = {}
        self._access_tokens = {}
        self._refresh_tokens = {}
        self._nonces = set()

    def get_user(self, sub: str) -> User | None:
        return self._users.get(sub)

    def store_user(self, user: User):
        self._users[user.sub] = user

    def get_authorization_code(self, code: str) -> AuthorizationCode | None:
        return self._authorization_codes.get(code)

    def store_authorization_code(self, code: AuthorizationCode):
        self._authorization_codes[code.code] = code

    def remove_authorization_code(self, code: str) -> AuthorizationCode | None:
        return self._authorization_codes.pop(code, None)

    def get_access_token(self, token: str) -> AccessToken | None:
        return self._access_tokens.get(token)

    def store_access_token(self, access_token: AccessToken):
        self._access_tokens[access_token.token] = access_token

    def remove_access_token(self, access_token: str):
        del self._access_tokens[access_token]

    def get_refresh_token(self, token: str) -> RefreshToken | None:
        return self._refresh_tokens.get(token)

    def store_refresh_token(self, refresh_token: RefreshToken):
        self._refresh_tokens[refresh_token.token] = refresh_token

    def get_client(self, id: str) -> Client | None:
        return self._clients.get(id)

    def store_client(self, client: Client):
        self._clients[client.id] = client

    def add_nonce(self, nonce: str):
        self._nonces.add(nonce)

    def exists_nonce(self, nonce: str) -> bool:
        return nonce in self._nonces


storage = cast(
    "Storage", werkzeug.local.LocalProxy(lambda: flask.g.oidc_provider_mock_storage)
)
