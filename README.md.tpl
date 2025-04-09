# OpenID Provider Mock

[![PyPI version](https://img.shields.io/pypi/v/oidc-provider-mock)](https://pypi.org/project/oidc-provider-mock/)
[![main](https://github.com/geigerzaehler/oidc-provider-mock/actions/workflows/main.yaml/badge.svg)](https://github.com/geigerzaehler/oidc-provider-mock/actions/workflows/main.yaml)
[![documentation](https://readthedocs.org/projects/oidc-provider-mock/badge/?version=latest)][docs]

> A mock OpenID Provider server to test and develop OpenID Connect
> authentication.

You can find the full documentation [here][docs].

[docs]: https://oidc-provider-mock.readthedocs.io/latest/

## Usage

The simplest method to run the server is
[`pipx`](https://pipx.pypa.io/latest/installation/):

```bash
$ pipx run oidc-provider-mock
Started OpenID provider http://localhost:9400
```

Now, configure your OpenID Connect client library in your app to use
`http://localhost:9400` as the issuer URL. By default, you can use any client ID
and client secret with the provider.

Finally, you can authenticate against the app (the Relying Party) through the
mock provider’s login form:

![Authorization form](https://oidc-provider-mock.readthedocs.io/latest/_static/auth-form.webp)

Take a look at the following example that uses the server in a test for a
[Flask-OIDC](https://flask-oidc.readthedocs.io/en/latest/) app.

```python
SNIPPET flask_test_login
```

For all full testing example, see
[`examples/flask_oidc_example.py`](examples/flask_oidc_example.py). You can find
more advanced tests in
[`tests/flask_advanced_test.py`](tests/flask_advanced_test.py).

If you’re using [Playwright](https://playwright.dev) for end-to-end tests, a
login test looks like this:

```python
SNIPPET flask_test_login_playwright
```

You can find a full example at
[`examples/flask_oidc_example.py`](examples/flask_oidc_example.py), too.

## Alternatives

There already exist a couple of OpendID provider servers for testing. This is
how they differ from this project (to the best of my knowledge):

[`axa-group/oauth2-mock-server`](https://github.com/axa-group/oauth2-mock-server)

- Does not offer a HTML login form where the subject can be input or
  authorization denied.
- Behavior can only be customized through the JavaScript API.

[`Soluto/oidc-server-mock`](https://github.com/Soluto/oidc-server-mock)

- Identities (users) and clients must be statically configured.
- Requires a non-trivial amount of configuration before it can be used.

[`oauth2-proxy/mockoidc`](https://github.com/oauth2-proxy/mockoidc`)

- Does not have a CLI, only available as a Go library

<https://oauth.wiremockapi.cloud/>

- Only a hosted version exists
- Claims and user info cannot be customized
- Cannot simulate errors
