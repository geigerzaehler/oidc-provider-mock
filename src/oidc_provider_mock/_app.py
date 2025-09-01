import logging
import secrets
import textwrap
import warnings
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from typing import TypeVar, cast
from uuid import uuid4

import authlib.deprecate
import authlib.integrations.flask_oauth2 as flask_oauth2
import authlib.oauth2.rfc6749
import authlib.oauth2.rfc6749.errors
import authlib.oauth2.rfc6750
import authlib.oidc.core
import flask
import flask.typing
import pydantic
import werkzeug.debug
import werkzeug.exceptions
import werkzeug.local
from authlib import jose
from authlib.integrations.flask_oauth2.authorization_server import FlaskOAuth2Request
from authlib.oauth2 import OAuth2Error, OAuth2Request
from typing_extensions import Never, override

from . import _client
from ._storage import (
    AccessToken,
    AuthorizationCode,
    Client,
    ClientAllowAny,
    ClientAuthMethod,
    RefreshToken,
    Storage,
    User,
    storage,
)

assert __package__
_logger = logging.getLogger(__package__)

_JWS_ALG = "RS256"


class TokenValidator(authlib.oauth2.rfc6750.BearerTokenValidator):
    @override
    def authenticate_token(self, token_string: str):  # pyright: ignore[reportIncompatibleMethodOverride]
        token = storage.get_access_token(token_string)
        if not token:
            raise authlib.oauth2.rfc6749.AccessDeniedError()

        return token


class AuthorizationCodeGrant(authlib.oauth2.rfc6749.AuthorizationCodeGrant):
    @override
    def query_authorization_code(  # pyright: ignore[reportIncompatibleMethodOverride]
        self, code: str, client: Client
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
        client = cast("Client", request.client)
        with warnings.catch_warnings():
            # Silence warnings for deprecated `OAuth2Request` properties.
            warnings.simplefilter("ignore", authlib.deprecate.AuthlibDeprecationWarning)
            assert isinstance(request.redirect_uri, str)  # pyright: ignore[reportDeprecated]
            storage.store_authorization_code(
                AuthorizationCode(
                    code=code,
                    user_id=request.user.sub,
                    client_id=client.get_client_id(),
                    redirect_uri=request.redirect_uri,  # pyright: ignore[reportDeprecated]
                    scope=request.scope,  # pyright: ignore[reportDeprecated]
                    nonce=request.data.get("nonce"),  # pyright: ignore[reportDeprecated]
                )
            )


class OpenIDCode(authlib.oidc.core.OpenIDCode):
    def __init__(self, require_nonce: bool, token_max_age: timedelta):
        super().__init__(require_nonce)
        self._token_max_mage = token_max_age

    @override
    def exists_nonce(self, nonce: str, request: OAuth2Request) -> bool:
        return storage.exists_nonce(nonce)

    @override
    def get_jwt_config(self, grant: authlib.oauth2.rfc6749.BaseGrant):  # pyright: ignore[reportIncompatibleMethodOverride]
        return {
            "key": storage.jwk,
            "alg": _JWS_ALG,
            "exp": int(self._token_max_mage.total_seconds()),
            "iss": flask.request.host_url.rstrip("/"),
        }

    @override
    def generate_user_info(self, user: User, scope: str):  # pyright: ignore[reportIncompatibleMethodOverride]
        return _user_claims_for_scope(user, scope)


class RefreshTokenGrant(authlib.oauth2.rfc6749.RefreshTokenGrant):
    @override
    def authenticate_refresh_token(self, refresh_token: str):
        token = storage.get_refresh_token(refresh_token)
        if not token:
            raise authlib.oauth2.rfc6749.InvalidGrantError("invalid refresh token")

        return token

    def authenticate_user(self, refresh_token: RefreshToken):
        return storage.get_user(refresh_token.user_id)

    def revoke_old_credential(self, refresh_token: authlib.oauth2.rfc6749.TokenMixin):
        assert isinstance(refresh_token, RefreshToken)
        storage.remove_access_token(refresh_token.access_token)


def _user_claims_for_scope(user: User, scope: str) -> dict[str, object]:
    scopes = scope.split(" ")
    allowed_standard_claims_for_scope = {
        claim for scope in scopes for claim in _SCOPES_TO_CLAIMS.get(scope, [])
    }

    return {
        **{
            name: value
            for name, value in user.claims.items()
            if name not in _STANDARD_CLAIMS or name in allowed_standard_claims_for_scope
        },
        "sub": user.sub,
    }


# https://openid.net/specs/openid-connect-core-1_0.html#ScopeClaims
_SCOPES_TO_CLAIMS: dict[str, Sequence[str]] = {
    "profile": [
        "name",
        "family_name",
        "given_name",
        "middle_name",
        "nickname",
        "preferred_username",
        "profile",
        "picture",
        "website",
        "gender",
        "birthdate",
        "zoneinfo",
        "locale",
        "updated_at",
    ],
    "email": ["email", "email_verified"],
    "address": ["address"],
    "phone": ["phone_number", "phone_number_verified"],
}

_STANDARD_CLAIMS = {claim for claims in _SCOPES_TO_CLAIMS.values() for claim in claims}


require_oauth = flask_oauth2.ResourceProtector()

authorization = cast(
    "flask_oauth2.AuthorizationServer",
    werkzeug.local.LocalProxy(lambda: flask.g._authlib_authorization_server),
)

blueprint = flask.Blueprint("oidc-provider-mock", __name__)


@dataclass(kw_only=True, frozen=True)
class Config:
    require_client_registration: bool = False
    require_nonce: bool = False
    issue_refresh_token: bool = True
    access_token_max_age: timedelta = timedelta(hours=1)


@blueprint.record
def setup(setup_state: flask.blueprints.BlueprintSetupState):
    assert isinstance(setup_state.app, flask.Flask)

    config = setup_state.options["config"]
    assert isinstance(config, Config)

    setup_state.app.config["OAUTH2_TOKEN_EXPIRES_IN"] = {
        "authorization_code": int(config.access_token_max_age.total_seconds()),
    }

    setup_state.app.config["OAUTH2_REFRESH_TOKEN_GENERATOR"] = (
        config.issue_refresh_token
    )

    authorization = flask_oauth2.AuthorizationServer()
    storage = Storage()

    @setup_state.app.before_request
    def set_globals():
        flask.g.oidc_provider_mock_storage = storage
        flask.g.oidc_provider_mock_config = config
        flask.g._authlib_authorization_server = authorization

    def query_client(id: str) -> Client | None:
        client = storage.get_client(id)
        if not client and not config.require_client_registration:
            client = Client(
                id=id,
                secret=ClientAllowAny(),
                redirect_uris=ClientAllowAny(),
                allowed_scopes=Client.SCOPES_SUPPORTED,
                token_endpoint_auth_method=ClientAllowAny(),
            )

        return client

    def save_token(token: dict[str, object], request: OAuth2Request):
        assert token["token_type"] == "Bearer"
        assert isinstance(token["access_token"], str)
        assert isinstance(token["expires_in"], int)
        assert isinstance(request.user, User)
        scope = token.get("scope", "")
        assert isinstance(scope, str)

        storage.store_access_token(
            AccessToken(
                token=token["access_token"],
                user_id=request.user.sub,
                # request.scope may actually be None
                scope=scope,
                expires_at=datetime.now(timezone.utc)
                + timedelta(seconds=token["expires_in"]),
            )
        )

        if "refresh_token" in token:
            assert isinstance(token["refresh_token"], str)
            assert isinstance(request.client, Client)

            storage.store_refresh_token(
                RefreshToken(
                    access_token=token["access_token"],
                    token=token["refresh_token"],
                    user_id=request.user.sub,
                    scope=scope,
                    expires_at=datetime.now(timezone.utc)
                    + timedelta(seconds=token["expires_in"]),
                    client_id=request.client.id,
                )
            )

    authorization.init_app(  # type: ignore
        setup_state.app,
        query_client=query_client,
        save_token=save_token,
    )

    authorization.register_grant(
        AuthorizationCodeGrant,
        [
            OpenIDCode(
                require_nonce=config.require_nonce,
                token_max_age=config.access_token_max_age,
            )
        ],
    )

    authorization.register_grant(RefreshTokenGrant)


@blueprint.record_once
def setup_once(setup_state: flask.blueprints.BlueprintSetupState):
    require_oauth.register_token_validator(TokenValidator())  # pyright: ignore[reportUnknownMemberType]


def app(
    *,
    require_client_registration: bool = False,
    require_nonce: bool = False,
    issue_refresh_token: bool = True,
    access_token_max_age: timedelta = timedelta(hours=1),
) -> flask.Flask:
    """Create a Flask app running the OpenID provider.

    Call ``app().run()`` (see `flask.Flask.run`) to start the server.

    See ``init_app`` for documentation of parameters
    """
    app = flask.Flask(__name__)

    init_app(
        app,
        require_client_registration=require_client_registration,
        require_nonce=require_nonce,
        issue_refresh_token=issue_refresh_token,
        access_token_max_age=access_token_max_age,
    )
    app.secret_key = secrets.token_bytes(16)
    if isinstance(app.json, flask.json.provider.DefaultJSONProvider):
        # Make it easier to debug responses
        app.json.compact = False
    return app


def init_app(
    app: flask.Flask,
    *,
    require_client_registration: bool = False,
    require_nonce: bool = False,
    issue_refresh_token: bool = True,
    access_token_max_age: timedelta = timedelta(hours=1),
):
    """Add the OpenID provider and its endpoints to the flask ``app``.

    :param require_client_registration: If false (the default) any client ID and
        secret can be used to authenticate with the token endpoint. If true,
        clients have to be registered using the `OAuth 2.0 Dynamic Client
        Registration Protocol <https://datatracker.ietf.org/doc/html/rfc7591>`_.
    :param require_nonce: If true, the authorization request must include the
        `nonce parameter`_ to prevent replay attacks. If the parameter is not
        provided the authorization request will fail.
    :param issue_refresh_token: If true (the default), the token endpoint response
        will include a refresh token.
    :param access_token_max_age: Max age of access and ID token after which it expires.

    .. _nonce parameter: https://openid.net/specs/openid-connect-core-1_0.html#AuthRequest
    """

    app.register_blueprint(
        blueprint,
        config=Config(
            require_client_registration=require_client_registration,
            require_nonce=require_nonce,
            issue_refresh_token=issue_refresh_token,
            access_token_max_age=access_token_max_age,
        ),
    )

    app.register_blueprint(_client.blueprint)

    app.debug = True
    app.wsgi_app = werkzeug.debug.DebuggedApplication(app.wsgi_app)
    app.wsgi_app.trusted_hosts.append("localhost")

    return app


@blueprint.get("/")
def home():
    return flask.render_template("index.html")


@blueprint.get("/.well-known/openid-configuration")
def openid_config():
    def url_for(fn: Callable[..., object]) -> str:
        return flask.url_for(f".{fn.__name__}", _external=True)

    # See https://openid.net/specs/openid-connect-discovery-1_0.html#ProviderMetadata
    # for information about the fields.
    return flask.jsonify({
        "issuer": flask.request.host_url.rstrip("/"),
        "authorization_endpoint": url_for(authorize),
        "token_endpoint": url_for(issue_token),
        "userinfo_endpoint": url_for(userinfo),
        "registration_endpoint": url_for(register_client),
        "jwks_uri": url_for(jwks),
        "response_types_supported": Client.RESPONSE_TYPES_SUPPORTED,
        "response_modes_supported": ["query"],
        "grant_types_supported": Client.GRANT_TYPES_SUPPORTED,
        "scopes_supported": Client.SCOPES_SUPPORTED,
        "id_token_signing_alg_values_supported": [_JWS_ALG],
    })


@blueprint.get("/jwks")
def jwks():
    return flask.jsonify(
        jose.KeySet((storage.jwk,)).as_dict(),  # pyright: ignore[reportUnknownMemberType]
    )


class RegisterClientBody(pydantic.BaseModel):
    redirect_uris: Sequence[pydantic.HttpUrl]
    token_endpoint_auth_method: ClientAuthMethod = "client_secret_basic"
    scope: str | None = None


@blueprint.post("/oauth2/clients")
def register_client():
    body = _validate_body(flask.request, RegisterClientBody)

    client = Client(
        id=str(uuid4()),
        secret=secrets.token_urlsafe(16),
        redirect_uris=[str(uri) for uri in body.redirect_uris],
        allowed_scopes=body.scope or Client.SCOPES_SUPPORTED,
        token_endpoint_auth_method=body.token_endpoint_auth_method,
    )

    storage.store_client(client)
    return flask.jsonify({
        "client_id": client.id,
        "client_secret": client.secret,
        "redirect_uris": client.redirect_uris,
        "token_endpoint_auth_method": body.token_endpoint_auth_method,
        "grant_types": Client.GRANT_TYPES_SUPPORTED,
        "response_types": Client.RESPONSE_TYPES_SUPPORTED,
    }), HTTPStatus.CREATED


@blueprint.route("/oauth2/authorize", methods=["GET", "POST"])
def authorize() -> flask.typing.ResponseReturnValue:
    request = FlaskOAuth2Request(flask.request)
    try:
        grant, redirect_uri = _validate_auth_request_client_params(flask.request)
        assert isinstance(grant.client, Client)  # pyright: ignore[reportUnknownMemberType]
    except _AuthorizationValidationException as exc:
        _logger.warning(f"invalid authorization request: {exc.description}")
        raise

    if flask.request.method == "GET":
        return flask.render_template(
            "authorization_form.html",
            redirect_uri=redirect_uri,
            client_id=grant.client.id,
        )
    else:
        if flask.request.form.get("action") == "deny":
            return authorization.handle_response(  # pyright: ignore[reportUnknownMemberType]
                *authlib.oauth2.rfc6749.AccessDeniedError(  # pyright: ignore[reportUnknownArgumentType]
                    redirect_uri=flask.request.args["redirect_uri"]
                )()
            )

        sub = flask.request.form.get("sub")
        if sub is None:
            return flask.render_template(
                "authorization_form.html",
                redirect_uri=redirect_uri,
                client_id=grant.client.id,
                sub_missing=True,
            )

        user = storage.get_user(sub)
        if not user:
            user = User(sub=sub, claims={"email": sub})
            storage.store_user(user)

        try:
            response = grant.create_authorization_response(redirect_uri, user)  # pyright: ignore
            _logger.info(
                "issued authorization code",
                extra=({"client": grant.client, "user": user}),
            )
            return authorization.handle_response(*response)  # pyright: ignore
        except authlib.oauth2.OAuth2Error as error:
            _logger.warning("invalid authorization request", exc_info=True)
            return authorization.handle_error_response(request, error)  # pyright: ignore


def _validate_auth_request_client_params(
    flask_request: flask.Request,
) -> tuple[AuthorizationCodeGrant | RefreshTokenGrant, str]:
    """Validate query parameters sent by the client to the authorization endpoint.

    Raises ``_AuthorizationValidationException`` if validation fails which results
    in an appropriate 400 response.
    """

    request = FlaskOAuth2Request(flask_request)

    try:
        grant = authorization.get_consent_grant()  # type: ignore
        assert isinstance(grant, AuthorizationCodeGrant)
        redirect_uri = grant.validate_authorization_request()
    except authlib.oauth2.rfc6749.InvalidClientError as e:
        raise _AuthorizationValidationException(
            authlib.oauth2.rfc6749.InvalidClientError.error,
            e.description,
        ) from e
    except authlib.oauth2.rfc6749.UnsupportedResponseTypeError as e:
        raise _AuthorizationValidationException(
            e.error,
            f"OAuth response_type {e.response_type} is not supported",
        ) from e
    except authlib.oauth2.rfc6749.InvalidRequestError as e:
        description = e.description
        # FIXME: this is a brittle way of determining what the error is but
        # authlib does not raise a dedicated error in this case.
        if description == "Redirect URI foo is not supported by client.":
            raise _AuthorizationValidationException(
                authlib.oauth2.rfc6749.InvalidClientError.error,
                description,
            ) from e
        else:
            raise werkzeug.exceptions.HTTPException(
                response=flask.make_response(
                    authorization.handle_error_response(request, e)
                )
            ) from e
    except authlib.oauth2.OAuth2Error as e:
        raise werkzeug.exceptions.HTTPException(
            response=flask.make_response(
                authorization.handle_error_response(request, e)
            )
        ) from e

    return grant, redirect_uri


class _AuthorizationValidationException(werkzeug.exceptions.HTTPException):
    error: str

    def __init__(self, error: str, description: str):
        self.error = error
        self.description = description
        response = flask.make_response(
            flask.render_template("error.html", name=error, description=description),
            HTTPStatus.BAD_REQUEST,
        )
        super().__init__(response=response)
        self.code = HTTPStatus.BAD_REQUEST


@blueprint.post("/oauth2/token")
def issue_token() -> flask.typing.ResponseReturnValue:
    request = FlaskOAuth2Request(flask.request)
    try:
        grant = authorization.get_token_grant(request)
    except authlib.oauth2.rfc6749.UnsupportedGrantTypeError as error:
        _logger.warning(
            "unsupported grant type for issuing token",
            extra={"grant_type": error.grant_type},
        )
        return authorization.handle_error_response(request, error)  # type: ignore

    assert isinstance(grant, AuthorizationCodeGrant | RefreshTokenGrant)

    try:
        grant.validate_token_request()
        args = grant.create_token_response()
        return authorization.handle_response(*args)  # type: ignore
    except OAuth2Error as error:
        if error.error:
            _logger.warning(
                f"token endpoint error {error.error}",
                extra={"description": error.description},
            )
        else:
            _logger.warning("error while issuing token", exc_info=error)
        return authorization.handle_error_response(request, error)  # type: ignore


@blueprint.route("/userinfo", methods=["GET", "POST"])
@require_oauth()
def userinfo():
    access_token = flask_oauth2.current_token
    assert isinstance(access_token, AccessToken)
    return flask.jsonify(
        _user_claims_for_scope(access_token.get_user(), access_token.scope)
    )


SetUserBody = pydantic.RootModel[dict[str, object]]


@blueprint.put("/users/<sub>")
def set_user(sub: str):
    body = _validate_body(flask.request, SetUserBody)
    storage.store_user(User(sub=sub, claims=body.root))
    return "", HTTPStatus.NO_CONTENT


@blueprint.post("/users/<sub>/revoke-tokens")
def revoke_user_tokens(sub: str):
    for access_token in storage.access_tokens():
        if access_token.user_id == sub:
            storage.remove_access_token(access_token.token)
    for refresh_token in storage.refresh_tokens():
        if refresh_token.user_id == sub:
            storage.remove_refresh_token(refresh_token.token)
    return "", HTTPStatus.NO_CONTENT


class InsecureTransportError(Exception):
    def __init__(self):
        super().__init__(
            "OAuth 2 requires https. Set the environment variable"
            "`AUTHLIB_INSECURE_TRANSPORT=1` to disable this check"
        )


def _insecure_transport_error_handler(
    error: authlib.oauth2.rfc6749.errors.InsecureTransportError,
) -> Never:
    raise InsecureTransportError() from error


blueprint.register_error_handler(
    authlib.oauth2.rfc6749.errors.InsecureTransportError,
    _insecure_transport_error_handler,
)

_Model = TypeVar("_Model", bound=pydantic.BaseModel)


def _validate_body(request: flask.Request, model: type[_Model]) -> _Model:
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
