import json
import random
import subprocess
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import httpx
import yaml
from faker import Faker
from inline_snapshot import snapshot

from .conftest import fake_client

faker = Faker()


def test_cli_help():
    result = subprocess.run(
        ["oidc-provider-mock", "--help"], capture_output=True, text=True, check=True
    )
    assert result.returncode == 0
    assert result.stdout == snapshot("""\
Usage: oidc-provider-mock [OPTIONS]

  Start an OpenID Connect Provider for testing

Options:
  -p, --port INTEGER              Port the server listens on  [default: 9400]
  -H, --host TEXT                 IP address to bind the server to  [default:
                                  127.0.0.1]
  -r, --require-registration BOOLEAN
                                  Require clients to register before they can
                                  request authentication  [default: False]
  -n, --require-nonce BOOLEAN     Require clients to include a nonce in the
                                  authorization request to prevent replay
                                  attacks  [default: False]
  -f, --no-refresh-token BOOLEAN  Do not issue an refresh token  [default:
                                  False]
  -e, --token-max-age INTEGER     Max age of access and ID tokens in seconds
                                  until they expire
  --user TEXT                     Predefined user subject (can be specified
                                  multiple times)
  --user-claims TEXT              Predefined user with claims as JSON (must
                                  include "sub" property, can be specified
                                  multiple times)
  --user-claims-file FILENAME     YAML or JSON file containing a list of
                                  predefined user claims
  -h, --help                      Show this message and exit.
""")


def test_cli_user_claims_file_missing_sub(tmp_path: Path):
    claims_file = tmp_path / "users.yaml"
    claims_file.write_text(yaml.dump([{"email": "alice@example.com"}]))

    result = subprocess.run(
        ["oidc-provider-mock", "--user-claims-file", str(claims_file)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    stderr = result.stderr.replace(str(claims_file), "<file>")
    assert (
        stderr
        == 'Error: --user-claims-file: user claims must include a "sub" property\n'
    )


def test_cli_user_claims_file(tmp_path: Path):
    claims_file = tmp_path / "users.yaml"
    claims_file.write_text(yaml.dump([{"sub": "alice", "email": "alice@example.com"}]))

    with _running_server(["--user-claims-file", str(claims_file)]) as base_url:
        state = faker.password()
        with fake_client(issuer=base_url) as client:
            response = httpx.post(
                client.authorization_url(state=state),
                data={"sub": "alice"},
            )
            assert response.status_code == 302

            token_data = client.fetch_token(response.headers["location"], state=state)
            assert token_data.claims["sub"] == "alice"
            assert token_data.claims["email"] == "alice@example.com"


def test_cli():
    with _running_server(["--user-claims", json.dumps({"sub": "foo"})]) as base_url:
        assert (
            httpx.get(f"{base_url}/.well-known/openid-configuration").json()["issuer"]
            == base_url
        )


@contextmanager
def _running_server(args: list[str], port: int | None = None) -> Iterator[str]:
    if port is None:
        port = random.randint(40001, 65535)
    base_url = f"http://127.0.0.1:{port}"
    with subprocess.Popen(
        ["oidc-provider-mock", "--port", str(port), *args], stdin=None, text=True
    ) as process:
        try:
            for _ in range(10):
                try:
                    httpx.get(
                        f"{base_url}/.well-known/openid-configuration"
                    ).raise_for_status()
                    break
                except (httpx.ConnectError, httpx.HTTPStatusError):
                    time.sleep(0.3)
            else:
                raise RuntimeError(f"Server at {base_url} did not start in time")
            yield base_url
        finally:
            process.terminate()
