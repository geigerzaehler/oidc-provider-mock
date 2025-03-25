# Usage

## Running the server

You can start the server using [`pipx`](https://pipx.pypa.io/latest/installation/):

```bash
pipx run oidc-provider-mock
```

You can also run the server programatically through the [Python API](project:#api).

## Client configuration

To use the mock provider, configure your OIDC client’s provider URL
(`http://localhost:9400` by default).

If your client library does not support discovery you will need to configure
the endpoint URLs individually. You can look up all endpoints at
<http://localhost:9400/.well-known/openid-configuration>.

You can use any client ID, client secret or redirect URI with the provider by
default. (See <project:#client-registration> for advanced usage)

## Authorization form

When a user needs to authenticate with the OIDC client the client redirects them
to the authorization endpoint of the provider. The authorization endpoint shows
the user the authorization form.

<div class="app-frame mac wireframe" style="margin: 2.5rem 2rem">
<img src="_static/auth-form.webp" alt="Authorization form">
</div>

The “sub” input is the user identifier (“subject”) that is included in the ID
token claims and user info response. By default, the value is also used for the
`email` claim. (See also <project:#setting-claims>)

When the user clicks “Authorize” they are redirected to the client application
and the app can obtain the OpenID token with information about the user.

When the user clicks “Deny” they are redirected to the client application with
an error that the app needs to handle.

## Client registration

By default, the provider works with any client ID and client secret.

The `--require-registration` flag requires client to register with the provider.
A client can be registered using the [OAuth2.0 Dynamic Client Registration
Protocol](https://datatracker.ietf.org/doc/html/rfc7591):

```bash
curl -XPOST localhost:9400/oauth2/clients \
   --json '{"redirect_uris": ["http://localhost:8000"]}'
```

The client ID and secret are contained in the response

```json
{
  "client_id": "050d5966-fb55-4887-a1fe-c9cd27d5386f",
  "client_secret": "yso-fwkXObTx5SEOLPDruQ",
  "grant_types": ["authorization_code", "refresh_token"],
  "redirect_uris": ["http://localhost:8000/"],
  "response_types": ["code"],
  "token_endpoint_auth_method": "client_secret_basic"
}
```

## Setting claims

By default, only the [OpenID Connect core claims][core claims] and the `email`
[standard claim][standard claims] are returned to the client in the ID token and
user info response. The value entered into the authentication form is used for
the `sub` and `email` claims.

Additional claims can be added to a user identified by their `sub` value through
the <project:#http_put_users> endpoint:

```bash
curl -XPUT localhost:9400/users/alice1 \
   --json '{"email": "alice@example.com", "custom": {"foo": 1}}'
```

If you authenticate as `alice1` the ID token and the user info response will
include the `email` and `custom` fields above.

### Scopes and claims

OpenID Connect [standard claims][] are only included in the ID token if the
client and authorization request have the appropriate scope.

Consider the following claims:

```bash
curl -XPUT localhost:9400/users/alice1 \
   --json '{"email": "alice@example.com", "name": "Alice"}'
```

The ID token contains the `email` and `name` claims only if `email` and
`profile` are included in the authorization scope.

The mapping from claims to scopes is documented in [“Requesting Claims using
Scope Values”][scope claims].

[core claims]: https://openid.net/specs/openid-connect-core-1_0.html#IDToken
[standard claims]: https://openid.net/specs/openid-connect-core-1_0.html#StandardClaims
[scope claims]: https://openid.net/specs/openid-connect-core-1_0.html#ScopeClaims
