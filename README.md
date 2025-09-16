<!-- THIS FILE HAS BEEN GENERATED FROM REAMDE.md.tpl -->
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

Alternatively, you can run the server as a container:

```bash
docker run -p 9400:9400 ghcr.io/geigerzaehler/oidc-provider-mock
```

See the [“Usage” documentation](https://oidc-provider-mock.readthedocs.io/stable/usage.html#running-the-server) for details.

Now, configure your OpenID Connect client library in your app to use
`http://localhost:9400` as the issuer URL. By default, you can use any client ID
and client secret with the provider.

Finally, you can authenticate against the app (the Relying Party) through the
mock provider’s login form:

![Authorization form](https://oidc-provider-mock.readthedocs.io/latest/_static/auth-form.webp)

Take a look at the following example that uses the server in a test for a
[Flask-OIDC](https://flask-oidc.readthedocs.io/en/latest/) app.

```python
@pytest.fixture
def oidc_server():
    with oidc_provider_mock.run_server_in_thread() as server:
        yield f"http://localhost:{server.server_port}"


def test_auth_code_login(client: flask.testing.FlaskClient, oidc_server: str):
    # Add OIDC claims for the user we want to authenticate
    response = httpx.put(
        f"{oidc_server}/users/{quote('alice@example.com')}",
        json={"email": "alice@example.com", "name": "Alice", "custom": ["foo", "bar"]},
    )
    assert response.status_code == 204

    # Start login on the client and get the authorization URL
    response = client.get("/login")
    assert response.location

    # Authorize the client by POSTing to the authorization URL.
    response = httpx.post(response.location, data={"sub": "alice@example.com"})

    # Go back to the client with the authorization code
    assert response.has_redirect_location
    response = client.get(response.headers["location"], follow_redirects=True)

    # Check that we have been authenticated
    assert response.text == "Welcome Alice (alice@example.com)"
```

For all full testing example, see
[`examples/flask_oidc_example.py`](examples/flask_oidc_example.py). You can find
more advanced tests in
[`tests/flask_advanced_test.py`](tests/flask_advanced_test.py).

If you’re using [Playwright](https://playwright.dev) for end-to-end tests, a
login test looks like this:

```python
def test_auth_code_login_playwright(
    live_server: LiveServer, oidc_server: str, page: Page
):
    # Let the OIDC provider know about the user’s email and name
    response = httpx.put(
        f"{oidc_server}/users/{quote('alice@example.com')}",
        json={"email": "alice@example.com", "name": "Alice"},
    )
    assert response.status_code == 204

    # Start login and be redirected to the provider
    page.goto(live_server.url("/login"))

    # Authorize with the provider
    page.get_by_placeholder("sub").fill("alice@example.com")
    page.get_by_role("button", name="Authorize").click()

    # Verify that we’re logged in
    expect(page.locator("body")).to_contain_text("Welcome Alice (alice@example.com)")
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

[`oauth2-proxy/mockoidc`](https://github.com/oauth2-proxy/mockoidc)

- Does not have a CLI, only available as a Go library

<https://oauth.wiremockapi.cloud/>

- Only a hosted version exists
- Claims and user info cannot be customized
- Cannot simulate errors
