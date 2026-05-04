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

from .conftest import fake_client

faker = Faker()


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
