import json
import subprocess
import time

import httpx


def test_only_predefined_users_requires_user():
    """--only-predefined-users must fail with a clear error if no users are given."""
    result = subprocess.run(
        ["oidc-provider-mock", "--only-predefined-users"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert (
        "--only-predefined-users requires at least one --user or --user-claims"
        in result.stdout + result.stderr
    )


def test_cli():
    with subprocess.Popen(
        ["oidc-provider-mock", "--user-claims", json.dumps({"sub": "foo"})],
        stdin=None,
        text=True,
    ) as process:
        try:
            base_url = "http://127.0.0.1:9400"
            response = None
            for _ in range(5):
                try:
                    response = httpx.get(f"{base_url}/.well-known/openid-configuration")
                except httpx.ConnectError:
                    time.sleep(0.5)

            assert response
            assert response.status_code == 200
            body = response.json()
            assert body["issuer"] == base_url
        finally:
            process.terminate()
