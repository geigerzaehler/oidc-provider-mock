import json
import subprocess
import time

import httpx


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
