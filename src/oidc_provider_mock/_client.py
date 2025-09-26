import secrets
from collections.abc import Callable
from http import HTTPStatus
from typing import Any

import flask
import htpy as h

from ._client_lib import AuthorizationError, OidcClient

blueprint = flask.Blueprint("oidc-client", __name__)


def _url_for(fn: Callable[..., object], **kwargs: Any) -> str:
    return flask.url_for(f".{fn.__name__}", **kwargs)


_SESSION_KEY_NONCE = "oidc_id_token_nonce"
_SESSION_KEY_STATE = "oidc_authorization_state"
_SESSION_KEY_OIDC_CLAIMS = "oidc_id_token_claims"


@blueprint.get("/oidc/login")
def login():
    state = secrets.token_urlsafe(16)
    nonce = secrets.token_urlsafe(16)
    flask.session[_SESSION_KEY_STATE] = state
    flask.session[_SESSION_KEY_NONCE] = nonce
    return _render_page(
        h.h1["Authenticate with OpenID Connect"],
        h.p[
            f"Start authentication with OpenID Connect Provider {flask.request.root_url}"
        ],
        h.form(method="post")[h.button["Start"]],
    )


@blueprint.post("/oidc/login")
def login_post():
    client = _get_client()
    state = secrets.token_urlsafe(16)
    nonce = secrets.token_urlsafe(16)
    flask.session[_SESSION_KEY_STATE] = state
    flask.session[_SESSION_KEY_NONCE] = nonce
    return flask.redirect(client.authorization_url(state=state, nonce=nonce))


@blueprint.get("/oidc/authorized")
def authorized():
    client = _get_client()
    if _SESSION_KEY_STATE not in flask.session:
        return _render_page(
            h.h1["Authentication Error"],
            h.p[
                "No authentication session in progress. ",
                h.a(href=_url_for(login))["Restart authentication"],
            ],
        )

    try:
        token_data = client.fetch_token(
            flask.request.url,
            state=flask.session[_SESSION_KEY_STATE],
        )
    except AuthorizationError as e:
        return _render_page(
            h.hgroup[h.h1["Authentication Error"], h.p[e.error]],
            h.p[e.description],
        ), HTTPStatus.BAD_REQUEST

    flask.session[_SESSION_KEY_OIDC_CLAIMS] = token_data.claims
    return flask.redirect(_url_for(success))


@blueprint.get("/oidc/success")
def success():
    claims = flask.session[_SESSION_KEY_OIDC_CLAIMS]
    return _render_page(
        h.h1["Authentication Success"],
        h.p["You’re logged in as ", h.mark[claims["sub"]]],
    )


def _get_client() -> OidcClient:
    return OidcClient(
        id="my-client-id",
        secret="my-client-secret",
        redirect_uri=_url_for(authorized, _external=True),
        issuer=flask.request.root_url,
    )


def _render_page(*content: h.Node) -> str:
    return flask.render_template("_base.html", content=h.fragment[content])
