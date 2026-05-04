# Test Structure

## Fixtures and configuration (conftest.py)

- `app` fixture: creates a Flask app, optionally configured via `@use_provider_config(...)` marker on the test
- `oidc_server` fixture: starts a real threaded HTTP server, yields its URL as a string
- `client` fixture: Flask test client (from Flask, not oidc-specific) — no real HTTP, no browser
- `page` fixture: Playwright browser page with 3s timeouts
- `use_provider_config(...)`: decorator that sets `Config` fields on the test's app — mirrors `Config` dataclass fields exactly (`require_client_registration`, `require_nonce`, `issue_refresh_token`, `access_token_max_age`, `user_claims`)
- `fake_client(issuer)`: creates an `OidcClient` with random ID/secret/redirect_uri, **not** registered with the server — works because `require_client_registration` defaults to `False`
- `typeguard` import hook is installed globally for `oidc_provider_mock` — runtime type checking is always active in tests

## Test files

| File | What it covers | Fixtures used |
|---|---|---|
| `auth_test.py` | Authorization code flow, claims (dynamic and preconfigured), nonce, access denied | `oidc_server` |
| `scope_test.py` | Scope filtering: openid required for ID token, claims excluded without scope, scope capped to registration | `oidc_server` |
| `token_test.py` | Token lifecycle: expiry, refresh rotation, revocation, unsupported grant type, expired token on userinfo | `oidc_server`, `client` |
| `client_registration_test.py` | Client registration enforcement, wrong secret, auth method validation | `oidc_server` |
| `auth_form_test.py` | Authorization form UI via Playwright; low-level form/query parameter validation via Flask test client | `oidc_server` + `page`, `client` |
| `end_session_test.py` | `/oauth2/end_session` endpoint: redirect, state, UI confirmation | `client`, `oidc_server` + `page` |
| `self_client_test.py` | Built-in OIDC client blueprint (`/oidc/login`) end-to-end via Playwright | `oidc_server` + `page` |
| `flask_advanced_test.py` | Integration with a real Flask-OIDC relying party (`examples/flask_oidc_example.py`); token refresh and expiry via time-freezing | `oidc_server` + `page`, custom `relying_party` fixture |
| `cli_test.py` | CLI smoke test: spawns `oidc-provider-mock` subprocess, polls discovery endpoint | subprocess only |
| `misc_test.py` | CORS headers, userinfo auth errors, `test_consistent_kwargs` (asserts `Config`, `init_app`, `run_server_in_thread`, and `use_provider_config` have identical kwargs) | `client` |

## Patterns

- `fake_client(issuer)` in `conftest.py`: use when the test doesn't need a registered client
- `OidcClient.register(oidc_server, ...)`: calls `POST /oauth2/clients` and returns a configured client — use when the test needs a specific redirect URI or scope
- Browser tests use Playwright's `expect(...)` assertions; non-browser tests use `httpx` for real HTTP or Flask's `client` for in-process requests
- `freeze_time` (freezegun) is used for token expiry tests
- `faker` generates random values for subjects, URIs, passwords, etc. — tests are not deterministic by design
