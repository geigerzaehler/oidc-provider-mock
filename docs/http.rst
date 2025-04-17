HTTP Endpoints
==============

.. _http_get_authorize:

``GET /oauth2/authorize``
-------------------------


OpenID Connect `authorization endpoint`_ that shows the authorization form to
the use. A relying party will redirect a user to this URL to authenticate them.
Submitting the form will redirect to the relying party that requested the
authentication.

Query parameters:

``client_id`` (required)
  ID of the client that requests authentication

``redirect_uri`` (required)
  Redirection URI to which the response will be sent

``response_type`` (required)
  Type of authorization response which also determines the OAuth2.0 flow.
  Currently, only ``code`` is supported.

.. _authorization endpoint: https://openid.net/specs/openid-connect-core-1_0.html#AuthorizationEndpoint

``POST /oauth2/authorize``
--------------------------

Endpoint for submitting authorization by the user. Redirects to ``redirect_uri``
with an authorization code or an error in the query.  Requires the same query
parameters as `http_get_authorize`.

Form parameters:

``sub`` (required unless ``action`` is ``deny``)
  The subject (or user identifier) to issue the authorization code for.

``action``
  If value is ``deny`` the user agent will be redirected to the client with an
  indication that the user denied the authorization.


.. _http_put_users:

``PUT /users/{sub}``
--------------------

Set user information to be included in the ID token and the userinfo endpoint.

The user is identified by ``sub``. The request body is a JSON document with the
claims that will be included in the ID token and user info response, for example

.. code:: json

    {
      "email": "alice@example.com"
      "nickname": "alice",
    }

A request overrides any previously set claims for the subject.

``POST /users/{sub}/revoke-tokens``
-----------------------------------

Revoke all access and refresh tokens for this user.
