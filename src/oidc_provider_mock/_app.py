import logging
import secrets
import textwrap
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from typing import TypedDict, TypeVar, cast
from uuid import uuid4

import authlib.oauth2.rfc6749
import authlib.oauth2.rfc6749.grants
import authlib.oauth2.rfc6750
import authlib.oidc.core.grants
import flask
import flask.typing
import pydantic
import werkzeug.exceptions
import werkzeug.local
from authlib import jose
from authlib.integrations import flask_oauth2
from authlib.integrations.flask_oauth2.authorization_server import FlaskOAuth2Request
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

_JWS_ALG = "RS256"


class TokenValidator(authlib.oauth2.rfc6750.BearerTokenValidator):
    def authenticate_token(self, token_string: str):
        token = storage.get_access_token(token_string)
        if not token:
            raise AccessDeniedError

        return token


class AuthorizationCodeGrant(authlib.oauth2.rfc6749.AuthorizationCodeGrant):
    @override
    def query_authorization_code(
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


class OpenIDCode(authlib.oidc.core.OpenIDCode):
    def exists_nonce(self, nonce: str, request: OAuth2Request) -> bool:
        return storage.exists_nonce(nonce)

    def get_jwt_config(self, *args: object, **kwargs: object):
        return {
            "key": storage.jwk,
            "alg": _JWS_ALG,
            "exp": 3600,
            "iss": flask.request.host_url.rstrip("/"),
        }

    def generate_user_info(self, user: User, scope: str):
        return _user_claims_for_scope(user, scope)


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

blueprint = flask.Blueprint("oidc-provider-mock-authlib", __name__)


class Config(TypedDict):
    require_client_registration: bool
    require_nonce: bool


@blueprint.record
def setup(setup_state: flask.blueprints.BlueprintSetupState):
    assert isinstance(setup_state.app, flask.Flask)

    config = Config(setup_state.options["config"])

    authorization = flask_oauth2.AuthorizationServer()
    storage = Storage()

    @setup_state.app.before_request
    def set_globals():
        flask.g.oidc_provider_mock_storage = storage
        flask.g._authlib_authorization_server = authorization

    def query_client(id: str) -> Client | None:
        client = storage.get_client(id)
        if not client and not config["require_client_registration"]:
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
        user = cast("User", request.user)
        scope = token.get("scope", "")
        assert isinstance(scope, str)

        storage.store_access_token(
            AccessToken(
                token=token["access_token"],
                user_id=user.sub,
                # request.scope may actually be None
                scope=scope,
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
        [OpenIDCode(require_nonce=config["require_nonce"])],
    )


@blueprint.record_once
def setup_once(setup_state: flask.blueprints.BlueprintSetupState):
    require_oauth.register_token_validator(TokenValidator())


def app(
    *,
    require_client_registration: bool = False,
    require_nonce: bool = False,
) -> flask.Flask:
    """Create a flask app for the OpenID provider.

    Call ``app().run()`` (see `flask.Flask.run`) to start the server.

    See ``init_app`` for documentaiton of parameters
    """
    app = flask.Flask(__name__)

    init_app(
        app,
        require_client_registration=require_client_registration,
        require_nonce=require_nonce,
    )
    return app


def init_app(
    app: flask.Flask,
    *,
    require_client_registration: bool = False,
    require_nonce: bool = False,
):
    """Add the OpenID provider and its endpoints to the app

    :param require_client_registration: If false (the default) any client ID and
        secret can be used to authenticate with the token endpoint. If true,
        clients have to be registered using the `OAuth 2.0 Dynamic Client
        Registration Protocol <https://datatracker.ietf.org/doc/html/rfc7591>`_.
    :param require_nonce: If true the authorization request must include the
        `nonce parameter`_ to prevent replay attacks. If the parameter is not
        provided the authorization request will fail.

    .. _nonce parameter: https://openid.net/specs/openid-connect-core-1_0.html#AuthRequest
    """

    app.register_blueprint(
        blueprint,
        config=Config(
            require_client_registration=require_client_registration,
            require_nonce=require_nonce,
        ),
    )
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


@blueprint.post("/register-client")
def register_client():
    body = _validate_body(flask.request, RegisterClientBody)

    client = Client(
        id=str(uuid4()),
        secret=secrets.token_urlsafe(16),
        redirect_uris=[str(uri) for uri in body.redirect_uris],
        allowed_scopes=Client.SCOPES_SUPPORTED,
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
    grant, redirect_uri = _validate_auth_request_client_params(flask.request)

    if flask.request.method == "GET":
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

        try:
            response = grant.create_authorization_response(redirect_uri, user)  # pyright: ignore
            return authorization.handle_response(*response)  # pyright: ignore
        except authlib.oauth2.OAuth2Error as error:
            return authorization.handle_error_response(request, error)  # pyright: ignore


def _validate_auth_request_client_params(
    flask_request: flask.Request,
) -> tuple[authlib.oauth2.rfc6749.AuthorizationEndpointMixin, str]:
    """Validate query parameters sent by the client to the authorization endpoint.

    Raises ``_AuthorizationValidationException`` if validation fails which results
    in an appropriate 400 response.
    """

    request = FlaskOAuth2Request(flask_request)

    try:
        grant = authorization.get_consent_grant()  # type: ignore
        assert isinstance(grant, authlib.oauth2.rfc6749.AuthorizationEndpointMixin)
        redirect_uri = grant.validate_authorization_request()  # pyright: ignore
        assert isinstance(redirect_uri, str)
    except authlib.oauth2.rfc6749.InvalidClientError as e:
        raise _AuthorizationValidationException(
            authlib.oauth2.rfc6749.InvalidClientError.error,
            "Invalid client_id query parameter",
        ) from e
    except authlib.oauth2.rfc6749.UnsupportedResponseTypeError as e:
        raise _AuthorizationValidationException(
            e.error,
            f"OAuth response_type {e.response_type} is not supported",
        ) from e
    except authlib.oauth2.rfc6749.InvalidRequestError as e:
        description = e.description  # type: ignore
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
                    authorization.handle_error_response(request, e)  # type: ignore
                )
            ) from e
    except authlib.oauth2.OAuth2Error as e:
        raise werkzeug.exceptions.HTTPException(
            response=flask.make_response(
                authorization.handle_error_response(request, e)  # type: ignore
            )
        ) from e

    return grant, redirect_uri


class _AuthorizationValidationException(werkzeug.exceptions.HTTPException):
    def __init__(self, name: str, description: str):
        response = flask.make_response(
            flask.render_template("error.html", name=name, description=description),
            HTTPStatus.BAD_REQUEST,
        )
        super().__init__(response=response)
        self.code = HTTPStatus.BAD_REQUEST


@blueprint.route("/oauth2/token", methods=["POST"])
def issue_token() -> flask.typing.ResponseReturnValue:
    return authorization.create_token_response()  # pyright: ignore


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
