# pyright: reportUnknownMemberType=none
"""Test OIDC login of a Flask app using
[Flask-OIDC](https://flask-oidc.readthedocs.io/en/stable/).
"""

from urllib.parse import quote

import httpx
import pytest
from freezegun import freeze_time
from playwright.sync_api import Page, expect

from examples import flask_oidc_example

from .conftest import TestServer, run_server, use_provider_config


@pytest.fixture
def relying_party(oidc_server: str):
    with run_server(flask_oidc_example.build_app(oidc_server)) as server:
        yield server


def test_refresh(relying_party: TestServer, page: Page, oidc_server: str):
    with freeze_time("1 Jan 2020", tick=True) as frozen_datetime:
        response = httpx.put(
            f"{oidc_server}/users/{quote('alice@example.com')}",
            json={"email": "alice@example.com", "name": "Alice"},
        )
        assert response.status_code == 204

        page.goto(relying_party.url("/login"))
        page.get_by_label("Subject").fill("alice@example.com")
        page.get_by_role("button", name="Authorize").click()

        expect(page.locator("body")).to_contain_text(
            "Welcome Alice (alice@example.com)"
        )

        frozen_datetime.tick(7200)
        page.reload()
        expect(page.locator("body")).to_contain_text(
            "Welcome Alice (alice@example.com)"
        )


@use_provider_config(issue_refresh_token=False)
def test_access_token_expired(relying_party: TestServer, oidc_server: str, page: Page):
    with freeze_time("1 Jan 2020", tick=True) as frozen_datetime:
        response = httpx.put(
            f"{oidc_server}/users/{quote('alice@example.com')}",
            json={"email": "alice@example.com", "name": "Alice"},
        )
        assert response.status_code == 204

        page.goto(relying_party.url("/login"))
        page.get_by_label("Subject").fill("alice@example.com")
        page.get_by_role("button", name="Authorize").click()

        expect(page.locator("body")).to_contain_text(
            "Welcome Alice (alice@example.com)"
        )

        frozen_datetime.tick(7200)
        page.reload()
        expect(page.locator("body")).to_contain_text("Not logged in")
