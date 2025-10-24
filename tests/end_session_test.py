from urllib.parse import urlencode

import flask.testing
import pytest
from faker import Faker
from playwright.sync_api import Page, expect

faker = Faker()


@pytest.mark.parametrize("method", ["GET", "POST"])
def test_id_token_hint(client: flask.testing.FlaskClient, method: str):
    response = client.open("/oauth2/end_session", method=method)
    assert response.status_code == 200
    assert "Recommended parameter <code>id_token_hint</code> not set" in response.text

    id_token_hint = faker.pystr()
    query = urlencode({
        "id_token_hint": id_token_hint,
    })
    response = client.open(f"/oauth2/end_session?{query}", method=method)
    assert response.status_code == 200
    assert (
        "Recommended parameter <code>id_token_hint</code> not set" not in response.text
    )


@pytest.mark.parametrize("method", ["GET", "POST"])
def test_post_logout_redirect_uri(client: flask.testing.FlaskClient, method: str):
    response = client.open("/oauth2/end_session", method=method)
    assert response.status_code == 200
    assert "You will be redirected to " not in response.text

    query = urlencode({
        "post_logout_redirect_uri": "/path",
    })
    response = client.open(f"/oauth2/end_session?{query}", method=method)
    assert response.status_code == 200
    assert "You will be redirected to <code>/path</code>" in response.text

    query = urlencode({
        "post_logout_redirect_uri": "/path?action=logout",
    })
    response = client.open(f"/oauth2/end_session?{query}", method=method)
    assert response.status_code == 200
    assert "You will be redirected to <code>/path?action=logout</code>" in response.text

    query = urlencode({
        "post_logout_redirect_uri": "/path?action=logout",
        "state": "the-state",
    })
    response = client.open(f"/oauth2/end_session?{query}", method=method)
    assert response.status_code == 200
    assert (
        "You will be redirected to <code>/path?action=logout&amp;state=the-state</code>"
        in response.text
    )


def test_end_session_confirm(oidc_server: str, page: Page):
    page.goto(f"{oidc_server}/oauth2/end_session")
    page.get_by_role("button", name="End session").click()
    expect(page.locator("body")).to_contain_text("Session ended")


def test_redirect_after_end_session_confirm(oidc_server: str, page: Page):
    query = urlencode({
        "post_logout_redirect_uri": "/path",
    })
    page.goto(f"{oidc_server}/oauth2/end_session?{query}")
    page.get_by_role("button", name="End session").click()
    expect(page).to_have_url(f"{oidc_server}path")

    query = urlencode({
        "post_logout_redirect_uri": "https://example.com/",
    })
    page.goto(f"{oidc_server}/oauth2/end_session?{query}")
    page.get_by_role("button", name="End session").click()
    expect(page).to_have_url("https://example.com/")

    state = faker.pystr()
    query = urlencode({
        "post_logout_redirect_uri": "https://example.com/",
        "state": state,
    })
    page.goto(f"{oidc_server}/oauth2/end_session?{query}")
    page.get_by_role("button", name="End session").click()
    expect(page).to_have_url(f"https://example.com/?state={state}")

    state = faker.pystr()
    query = urlencode({
        "post_logout_redirect_uri": "https://example.com/?action=logout",
        "state": state,
    })
    page.goto(f"{oidc_server}/oauth2/end_session?{query}")
    page.get_by_role("button", name="End session").click()
    expect(page).to_have_url(f"https://example.com/?action=logout&state={state}")
