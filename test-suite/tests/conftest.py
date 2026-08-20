"""
Shared fixtures and assertion helpers for the whole suite.

The key design points:

* Tests are black box. They only ever talk to the build through the HTTP
  contract, never by importing its code or reading its database. This is what
  lets one suite run unchanged against all nine builds.

* Success is checked strictly (the contract fixes the success status codes),
  but rejection is checked loosely. The task instruction left error responses
  to each model's discretion, so a rejected request is treated as "anything
  that is not a success", and, where money is involved, is confirmed by
  checking that no balance changed. This avoids failing a build merely for
  choosing status 400 over 422.
"""

import pytest
from api import Api, unique_email


DEFAULT_PASSWORD = "Str0ng-Passw0rd!"


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------

@pytest.fixture(scope="session")
def api():
    """A single HTTP client for the whole run."""
    client = Api()
    yield client
    client.close()


@pytest.fixture
def new_user(api):
    """
    Factory that registers and logs in a fresh user, returning a small object
    carrying the token and email. Use it whenever a test needs an account.
    """
    def _make():
        email = unique_email()
        reg = api.register(email, DEFAULT_PASSWORD)
        assert is_success(reg), f"registration failed: {reg.status_code} {reg.text}"

        login = api.login(email, DEFAULT_PASSWORD)
        assert is_success(login), f"login failed: {login.status_code} {login.text}"
        token = login.json()["access_token"]

        return _User(email=email, password=DEFAULT_PASSWORD, token=token)

    return _make


@pytest.fixture
def funded_user(api, new_user):
    """A user with a known starting balance, for tests that need money present."""
    def _make(amount_pence: int):
        user = new_user()
        resp = api.deposit(user.token, amount_pence)
        assert is_success(resp), f"funding deposit failed: {resp.status_code} {resp.text}"
        return user
    return _make


class _User:
    def __init__(self, email, password, token):
        self.email = email
        self.password = password
        self.token = token


# --------------------------------------------------------------------------
# Assertion helpers
# --------------------------------------------------------------------------

def is_success(resp) -> bool:
    return 200 <= resp.status_code < 300


def assert_success(resp, code=None):
    assert is_success(resp), f"expected success, got {resp.status_code}: {resp.text}"
    if code is not None:
        assert resp.status_code == code, (
            f"expected status {code}, got {resp.status_code}: {resp.text}"
        )


def assert_rejected(resp):
    """A rejected request is anything that is not a 2xx success."""
    assert not is_success(resp), (
        f"expected the request to be rejected, but it succeeded: {resp.text}"
    )


def balance(api, user) -> int:
    """Read a user's current balance in pence from GET /accounts/me."""
    resp = api.me(user.token)
    assert_success(resp, 200)
    return resp.json()["balance_pence"]
