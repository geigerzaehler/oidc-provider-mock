from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import cast

import authlib.oauth2.rfc6749
import authlib.oidc.core
import flask
import werkzeug.local
from authlib import jose
from typing_extensions import override


class ClientSkipVerification:
    """Special value for client secret and redirect URIs that indicates that
    verification is skipped."""


@dataclass(kw_only=True, frozen=True)
class Client:
    id: str
    secret: str | ClientSkipVerification
    redirect_uris: Sequence[str] | ClientSkipVerification
    allowed_scopes: Sequence[str] = ("openid", "profile")


@dataclass(kw_only=True, frozen=True)
class User:
    sub: str
    claims: dict[str, str] = field(default_factory=dict)
    userinfo: dict[str, object] = field(default_factory=dict)


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

    def get_user(self):
        return storage.get_user(self.user_id)

    # Implement `TokenMixin`

    @override
    def check_client(self, client: Client):
        # TODO implement
        return True

    @override
    def is_expired(self):
        return datetime.now(timezone.utc) >= self.expires_at

    @override
    def is_revoked(self):
        return False

    @override
    def get_scope(self) -> str:
        return self.scope


class Storage:
    jwk: jose.RSAKey

    _clients: dict[str, Client]
    _users: dict[str, User]
    _authorization_codes: dict[str, AuthorizationCode]
    _access_tokens: dict[str, AccessToken]
    _nonces: set[str]

    def __init__(self) -> None:
        self.jwk = jose.RSAKey.generate_key(is_private=True)  # pyright: ignore[reportUnknownMemberType]
        self._users = {}
        self._authorization_codes = {}
        self._access_tokens = {}
        self._nonces = set()
        self._clients = {}

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
