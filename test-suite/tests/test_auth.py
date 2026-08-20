"""
Registration, login, and authentication gating.

Covers FR1, FR2, and the authentication half of NFR2.
"""

from conftest import assert_success, assert_rejected, DEFAULT_PASSWORD
from api import unique_email


def test_register_new_user(api):
    """FR1: a visitor can register with an email and password."""
    resp = api.register(unique_email(), DEFAULT_PASSWORD)
    assert_success(resp, 201)
    body = resp.json()
    assert "user_id" in body
    assert "email" in body


def test_register_does_not_return_password(api):
    """NFR1 (partial): the stored password must never be echoed back."""
    resp = api.register(unique_email(), DEFAULT_PASSWORD)
    assert_success(resp, 201)
    assert DEFAULT_PASSWORD not in resp.text


def test_register_rejects_duplicate_email(api):
    """FR1: an email address is unique; the second registration is rejected."""
    email = unique_email()
    first = api.register(email, DEFAULT_PASSWORD)
    assert_success(first, 201)
    second = api.register(email, DEFAULT_PASSWORD)
    assert_rejected(second)


def test_login_returns_token(api):
    """FR2: a registered user can log in and receive a credential."""
    email = unique_email()
    api.register(email, DEFAULT_PASSWORD)
    resp = api.login(email, DEFAULT_PASSWORD)
    assert_success(resp, 200)
    assert "access_token" in resp.json()


def test_login_rejects_wrong_password(api):
    """FR2: login with the wrong password is rejected."""
    email = unique_email()
    api.register(email, DEFAULT_PASSWORD)
    resp = api.login(email, "not-the-password")
    assert_rejected(resp)


def test_login_rejects_unknown_user(api):
    """FR2: login for an address that was never registered is rejected."""
    resp = api.login(unique_email(), DEFAULT_PASSWORD)
    assert_rejected(resp)


def test_balance_requires_authentication(api):
    """NFR2: a protected endpoint rejects a request with no credential."""
    resp = api.me(token="")
    assert_rejected(resp)


def test_deposit_requires_authentication(api):
    """NFR2: money movement rejects a request with no credential."""
    resp = api.deposit(token="", amount_pence=1000)
    assert_rejected(resp)


def test_rejects_invalid_token(api):
    """NFR2: a made-up credential does not grant access."""
    resp = api.me(token="clearly-not-a-real-token")
    assert_rejected(resp)
