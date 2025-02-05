HTTP Endpoints
==============

``GET /oauth2/authorize``
-------------------------


OpenID Connect `authorization endpoint`_. On a ``GET``, show an authentication
form to the user. Submitting the form will redirect to the relying party that
requested the authentication.

Query parameters:

``client_id`` (required)
  ID of the client that requests authentication

``redirect_uri`` (required)
  Redirection URI to which the response will be sent

``response_type`` (required)
  Type of authorization response which also determines the OAuth2.0 flow.
  Currently, only ``code`` is supported.

.. _authorization endpoint: https://openid.net/specs/openid-connect-core-1_0.html#AuthorizationEndpoint


.. _http_put_users:

``PUT /users/{sub}``
----------------------

Set user information to be included in the ID token and the userinfo endpoint.

The user is identified by ``sub``. The request body is a JSON document with the
claims that will be included in the ID token and user info response, for example

.. code:: json

    {
      "email": "alice@example.com"
      "nickname": "alice",
    }

A request overrides any previously set claims for the subject.
