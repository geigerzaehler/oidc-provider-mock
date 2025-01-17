import logging
import secrets
import textwrap
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from typing import TypeVar, cast
from uuid import uuid4

import authlib.oauth2.rfc6749
import authlib.oauth2.rfc6749.grants
import authlib.oauth2.rfc6750
import authlib.oidc.core.grants
import flask
import flask.typing
import pydantic
import werkzeug.exceptions
from authlib import jose
from authlib.integrations import flask_oauth2
from authlib.oauth2 import OAuth2Request
from authlib.oauth2.rfc6749 import AccessDeniedError
from typing_extensions import override

from ._storage import (
    AccessToken,
    AuthorizationCode,
    Client,
    ClientAllowAny,
    ClientAuthMethod,
    Storage,
    User,
    storage,
)

assert __package__
_logger = logging.getLogger(__package__)


class AuthlibClient(authlib.oauth2.rfc6749.ClientMixin):
    """Wrap ``Client`` to implement authlib’s client protocol."""

    def __init__(self, client: Client) -> None:
        self._client = client

    @override
    def get_client_id(self):
        return self._client.id

    @override
    def get_default_redirect_uri(self) -> str:
        raise NotImplementedError()

    @override
    def get_allowed_scope(self, scope: str) -> str:
        return " ".join(s for s in scope.split() if s in self._client.allowed_scopes)

    @override
    def check_redirect_uri(self, redirect_uri: str) -> bool:
        if isinstance(self._client.redirect_uris, ClientAllowAny):
            return True

        return redirect_uri in self._client.redirect_uris

    @override
    def check_client_secret(self, client_secret: str) -> bool:
        if isinstance(self._client.secret, ClientAllowAny):
            return True

        return client_secret == self._client.secret

    @override
    def check_endpoint_auth_method(self, method: str, endpoint: object):
        if isinstance(self._client.token_endpoint_auth_method, ClientAllowAny):
            return True

        return method == self._client.token_endpoint_auth_method.value

    # TODO
    @override
    def check_grant_type(self, grant_type: str):
        return True

    @override
    def check_response_type(self, response_type: str):
        return response_type == "code"


class TokenValidator(authlib.oauth2.rfc6750.BearerTokenValidator):
    def authenticate_token(self, token_string: str):
        token = storage.get_access_token(token_string)
        if not token:
            raise AccessDeniedError

        return token


class AuthorizationCodeGrant(authlib.oauth2.rfc6749.AuthorizationCodeGrant):
    @override
    def query_authorization_code(
        self, code: str, client: AuthlibClient
    ) -> AuthorizationCode | None:
        auth_code = storage.get_authorization_code(code)
        if auth_code and auth_code.client_id == client.get_client_id():
            return auth_code

    @override
    def delete_authorization_code(self, authorization_code: AuthorizationCode):
        storage.remove_authorization_code(authorization_code.code)

    @override
    def authenticate_user(self, authorization_code: AuthorizationCode) -> User | None:
        return storage.get_user(authorization_code.user_id)

    @override
    def save_authorization_code(self, code: str, request: object):
        assert isinstance(request, OAuth2Request)
        assert isinstance(request.user, User)
        client = cast("AuthlibClient", request.client)
        assert isinstance(request.redirect_uri, str)  # type: ignore
        storage.store_authorization_code(
            AuthorizationCode(
                code=code,
                user_id=request.user.sub,
                client_id=client.get_client_id(),
                redirect_uri=request.redirect_uri,
                scope=request.scope,
                nonce=request.data.get("nonce"),  # type: ignore
            )
        )


class OpenIdGrantExtension:
    def exists_nonce(self, nonce: str, request: OAuth2Request) -> bool:
        return storage.exists_nonce(nonce)

    def get_jwt_config(self, *args: object, **kwargs: object):
        return {
            "key": storage.jwk,
            "alg": "RS256",
            "exp": 3600,
            "iss": flask.request.host_url.rstrip("/"),
        }

    def generate_user_info(self, user: User, scope: Sequence[str]):
        return {
            **user.claims,
            "sub": user.sub,
        }


class OpenIDCode(OpenIdGrantExtension, authlib.oidc.core.OpenIDCode):
    pass


class ImplicitGrant(OpenIdGrantExtension, authlib.oidc.core.OpenIDImplicitGrant):
    pass


class HybridGrant(OpenIdGrantExtension, authlib.oidc.core.OpenIDHybridGrant):
    pass


# TODO: turn  into context variables
authorization = flask_oauth2.AuthorizationServer()
require_oauth = flask_oauth2.ResourceProtector()


blueprint = flask.Blueprint("oidc-provider-mock-authlib", __name__)


@dataclass(kw_only=True, frozen=True)
class Config:
    require_client_registration: bool = False


@blueprint.record
def setup(setup_state: flask.blueprints.BlueprintSetupState):
    assert isinstance(setup_state.app, flask.Flask)

    config = setup_state.options.get("config", Config())
    if not isinstance(config, Config):
        raise TypeError(
            f"Expected {Config.__name__} as `config` option for blueprint, got {type(config)}"
        )

    storage = Storage()

    @setup_state.app.before_request
    def set_storage():
        flask.g.oidc_provider_mock_storage = storage

    def query_client(id: str) -> AuthlibClient | None:
        client = storage.get_client(id)
        if not client and not config.require_client_registration:
            client = Client(
                id=id,
                secret=ClientAllowAny(),
                redirect_uris=ClientAllowAny(),
                token_endpoint_auth_method=ClientAllowAny(),
            )

        if client:
            return AuthlibClient(client)

    def save_token(token: dict[str, object], request: OAuth2Request):
        assert token["token_type"] == "Bearer"
        assert isinstance(token["access_token"], str)
        assert isinstance(token["expires_in"], int)
        assert isinstance(request.user, User)
        user = cast("User", request.user)

        storage.store_access_token(
            AccessToken(
                token=token["access_token"],
                user_id=user.sub,
                # request.scope may actually be None
                scope=request.scope or "",
                expires_at=datetime.now(timezone.utc)
                + timedelta(seconds=token["expires_in"]),
            )
        )

    authorization.init_app(  # type: ignore
        setup_state.app,
        query_client=query_client,
        save_token=save_token,
    )

    authorization.register_grant(  # type: ignore
        AuthorizationCodeGrant,
        # TODO: Make this configurable
        [OpenIDCode(require_nonce=False)],
    )
    authorization.register_grant(ImplicitGrant)  # type: ignore
    authorization.register_grant(HybridGrant)  # type: ignore

    require_oauth.register_token_validator(TokenValidator())


def app(*, require_client_registration: bool = False) -> flask.Flask:
    """Create a flask app for the OpenID provider.

    Call ``app().run()`` (see `flask.Flask.run`) to start the server.


    :param require_client_registration: If false (the default) any client ID and
        secret can be used to authenticate with the token endpoint. If true,
        clients have to be registered using the `OAuth 2.0 Dynamic Client
        Registration Protocol <https://datatracker.ietf.org/doc/html/rfc7591>`_.
    """
    app = flask.Flask(__name__)

    app.register_blueprint(
        blueprint,
        config=Config(require_client_registration=require_client_registration),
    )
    return app


@blueprint.get("/")
def home():
    return flask.render_template("index.html")


@blueprint.get("/.well-known/openid-configuration")
def openid_config():
    def url_for(fn: Callable[..., object]) -> str:
        return flask.url_for(f".{fn.__name__}", _external=True)

    return flask.jsonify({
        "issuer": flask.request.host_url.rstrip("/"),
        "authorization_endpoint": url_for(authorize),
        "token_endpoint": url_for(issue_token),
        "userinfo_endpoint": url_for(userinfo),
        "registration_endpoint": url_for(register_client),
        "jwks_uri": url_for(jwks),
        # TODO properly populate these
        "response_types_supported": ["code", "id_token", "id_token token"],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": ["RS256"],
    })


@blueprint.get("/jwks")
def jwks():
    return flask.jsonify(
        jose.KeySet((storage.jwk,)).as_dict(),  # pyright: ignore[reportUnknownMemberType]
    )


class RegisterClientBody(pydantic.BaseModel):
    redirect_uris: Sequence[pydantic.HttpUrl]
    token_endpoint_auth_method: ClientAuthMethod = ClientAuthMethod.SecretBasic


@blueprint.post("/register-client")
def register_client():
    body = RegisterClientBody.model_validate(flask.request.json)

    client = Client(
        id=str(uuid4()),
        secret=secrets.token_urlsafe(16),
        redirect_uris=[str(uri) for uri in body.redirect_uris],
        token_endpoint_auth_method=body.token_endpoint_auth_method,
    )

    storage.store_client(client)
    return flask.jsonify({
        "client_id": client.id,
        "client_secret": client.secret,
        "redirect_uris": client.redirect_uris,
        "token_endpoint_auth_method": body.token_endpoint_auth_method.value,
        # For now, limit the accepted flow configuration
        "grant_types": ["authorization_code"],
        "response_types": ["code"],
    }), HTTPStatus.CREATED


@blueprint.route("/oauth2/authorize", methods=["GET", "POST"])
def authorize() -> flask.typing.ResponseReturnValue:
    if flask.request.method == "GET":
        # Validates request parameters
        try:
            authorization.get_consent_grant()  # type: ignore
        except authlib.oauth2.rfc6749.errors.InvalidClientError as e:
            raise NotImplementedError() from e

        return flask.render_template("authorization_form.html")
    else:
        if flask.request.form.get("action") == "deny":
            return authorization.handle_response(  # pyright: ignore[reportUnknownMemberType]
                *AccessDeniedError(redirect_uri=flask.request.args["redirect_uri"])()
            )

        # TODO: validate sub
        user = storage.get_user(flask.request.form["sub"])
        if not user:
            user = User(sub=flask.request.form["sub"])
            storage.store_user(user)
        return authorization.create_authorization_response(grant_user=user)  # type: ignore


@blueprint.route("/oauth2/token", methods=["POST"])
def issue_token() -> flask.typing.ResponseReturnValue:
    return authorization.create_token_response()  # pyright: ignore


@blueprint.route("/userinfo", methods=["GET", "POST"])
@require_oauth()
def userinfo():
    # TODO implement filtering by scope
    return flask.jsonify({
        **flask_oauth2.current_token.get_user().userinfo,
        "sub": flask_oauth2.current_token.user_id,
    })


class SetUserBody(pydantic.BaseModel):
    claims: dict[str, str] = pydantic.Field(default_factory=dict)
    userinfo: dict[str, object] = pydantic.Field(default_factory=dict)


@blueprint.put("/users/<sub>")
def set_user(sub: str):
    body = validate_body(flask.request, SetUserBody)
    storage.store_user(User(sub=sub, claims=body.claims, userinfo=body.userinfo))
    return "", HTTPStatus.NO_CONTENT


_Model = TypeVar("_Model", bound=pydantic.BaseModel)


def validate_body(request: flask.Request, model: type[_Model]) -> _Model:
    _logger.error("JO")
    try:
        return model.model_validate(request.json, strict=True)
    except pydantic.ValidationError as error:
        _logger.info(
            f"invalid request body {request.method} {request.url}\n{textwrap.indent(str(error), '  ')}",
            extra={
                "_msg": "invalid request body",
                "method": request.method,
                "url": request.url,
                "error": error,
            },
        )

        # TODO: support content type negotiation with html and json
        msg = "Invalid body:\n"
        for detail in error.errors():
            loc = detail.get("loc")
            if loc:
                msg += f"- {_pydantic_loc_to_path(loc)}:"
            msg += f" {detail.get('msg')}\n"

        raise werkzeug.exceptions.HTTPException(
            response=flask.make_response(
                msg,
                HTTPStatus.BAD_REQUEST,
                {"content-type": "text/plain; charset=utf-8"},
            )
        ) from error


def _pydantic_loc_to_path(loc: tuple[str | int, ...]) -> str:
    path = ""
    for i, x in enumerate(loc):
        match x:
            case str():
                if i > 0:
                    path += "."
                path += x
            case int():
                path += f"[{x}]"
    return path
