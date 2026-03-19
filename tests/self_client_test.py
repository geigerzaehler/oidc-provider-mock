import re

from faker import Faker
from playwright.sync_api import Page, expect

faker = Faker()


# @use_provider_config(require_client_registration=True)
def test_auth_success(oidc_server: str, page: Page):
    subject = faker.email()

    page.goto(f"{oidc_server}/oidc/login")
    page.get_by_role("button", name="Start").click()
    expect(page.get_by_role("heading", level=1)).to_have_text("Authorize Client")
    page.get_by_label("Subject").fill(subject)
    page.get_by_role("button", name=re.compile(r"^Authorize")).click()
    expect(page.locator("body")).to_contain_text(f"You’re logged in as {subject}")


def test_auth_deny(oidc_server: str, page: Page):
    page.goto(f"{oidc_server}/oidc/login")
    page.get_by_role("button", name="Start").click()
    page.get_by_role("button", name="Deny access").click()
    expect(page.get_by_role("heading")).to_have_text("Authentication Error")
    expect(page.locator("body")).to_contain_text("access_denied")
