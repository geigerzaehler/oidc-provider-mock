HTTP Endpoints
==============

.. _http_get_authorize:

``GET /oauth2/authorize``
-------------------------

OpenID Connect `authorization endpoint`_ that displays the authorization form.
A relying party redirects the user here to authenticate them. Submitting the
form redirects back to the relying party.

Query parameters:

``client_id`` (required)
  ID of the client requesting authentication.

``redirect_uri`` (required)
  URI to redirect the response to.

``response_type`` (required)
  Determines the authorization response type and OAuth 2.0 flow. Only ``code``
  is supported.

``nonce``
  Random value that will be included in the ID token to bind it to the
  authorization request. Required when the server is configured with
  :func:`require_nonce <oidc_provider_mock.init_app>`.

.. _authorization endpoint: https://openid.net/specs/openid-connect-core-1_0.html#AuthorizationEndpoint

``POST /oauth2/authorize``
--------------------------

Submit the authorization form. Redirects to ``redirect_uri`` with an
authorization code, or an error if authorization failed. Accepts the same query
parameters as :ref:`http_get_authorize`.

Form parameters:

``sub`` (required unless ``action`` is ``deny``)
  Subject identifier to issue the authorization code for.

``action``
  Set to ``deny`` to redirect the user agent back to the client with an access
  denied error.

``POST /oauth2/clients``
------------------------

Register a new OAuth 2.0 client (`dynamic client registration`_). Returns a
``client_id`` and ``client_secret`` that the client can use to authenticate
with the token endpoint.

Request body (JSON):

``redirect_uris`` (required)
  List of allowed redirect URIs.

``token_endpoint_auth_method``
  How the client authenticates at the token endpoint. One of
  ``client_secret_basic`` (default), ``client_secret_post``, or ``none``.

``scope``
  Space-separated list of scopes the client may request. Defaults to all
  supported scopes: ``openid``, ``profile``, ``email``, ``address``,
  ``phone``.

Response (``201 Created``):

.. code:: json

    {
      "client_id": "...",
      "client_secret": "...",
      "redirect_uris": ["https://example.com/callback"],
      "token_endpoint_auth_method": "client_secret_basic",
      "grant_types": ["authorization_code", "refresh_token"],
      "response_types": ["code"]
    }

.. _dynamic client registration: https://www.rfc-editor.org/rfc/rfc7591

.. _http_put_users:

``PUT /users/{sub}``
--------------------

Set claims for a user to be included in the ID token and userinfo endpoint.

``{sub}`` identifies the user to update. The request body is a JSON object
whose keys are claim names; any ``sub`` key in the JSON body is ignored:

.. code:: json

    {
      "email": "alice@example.com",
      "nickname": "alice"
    }

A request replaces any previously set claims for the subject.

``POST /users/{sub}/revoke-tokens``
-----------------------------------

Revoke all access and refresh tokens issued for this user.
