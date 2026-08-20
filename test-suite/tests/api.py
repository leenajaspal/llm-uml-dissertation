"""
Thin wrapper around the wallet's HTTP contract.

Every request the test suite makes goes through this class, so the endpoint
paths and field names live in exactly one place. This is the contract that was
fixed in the task instruction and given to every model, so the same wrapper
works against all nine builds without modification.

The wrapper is deliberately "dumb": it sends requests and returns the raw
response. All checking of what the response should contain is done in the
tests, so that this file never has to change between builds.
"""

import os
import uuid
import httpx


# Each build runs on its own server. Point the suite at the build under test by
# setting BASE_URL, e.g.  BASE_URL=http://localhost:8000  pytest
BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")

# How long to wait for a response before treating the build as unresponsive.
TIMEOUT = 10.0

# The daily limit from BR3, expressed in pence (£1,000).
DAILY_LIMIT_PENCE = 100_000


def unique_email() -> str:
    """A fresh email for every user, so re-running the suite never collides."""
    return f"user_{uuid.uuid4().hex[:12]}@example.com"


class Api:
    """One method per endpoint in the fixed contract."""

    def __init__(self, base_url: str = BASE_URL):
        self._client = httpx.Client(base_url=base_url, timeout=TIMEOUT)

    def close(self):
        self._client.close()

    # --- authentication -------------------------------------------------

    def register(self, email: str, password: str) -> httpx.Response:
        return self._client.post(
            "/auth/register",
            json={"email": email, "password": password},
        )

    def login(self, email: str, password: str) -> httpx.Response:
        return self._client.post(
            "/auth/login",
            json={"email": email, "password": password},
        )

    # --- account --------------------------------------------------------

    def me(self, token: str) -> httpx.Response:
        return self._client.get("/accounts/me", headers=self._auth(token))

    # --- money movement -------------------------------------------------

    def deposit(self, token: str, amount_pence) -> httpx.Response:
        return self._client.post(
            "/deposits",
            headers=self._auth(token),
            json={"amount_pence": amount_pence},
        )

    def withdraw(self, token: str, amount_pence) -> httpx.Response:
        return self._client.post(
            "/withdrawals",
            headers=self._auth(token),
            json={"amount_pence": amount_pence},
        )

    def transfer(self, token: str, recipient_email: str, amount_pence) -> httpx.Response:
        return self._client.post(
            "/transfers",
            headers=self._auth(token),
            json={"recipient_email": recipient_email, "amount_pence": amount_pence},
        )

    # --- history and reversal ------------------------------------------

    def transactions(self, token: str) -> httpx.Response:
        return self._client.get("/transactions", headers=self._auth(token))

    def reversal(self, token: str, transaction_id) -> httpx.Response:
        return self._client.post(
            f"/transactions/{transaction_id}/reversal",
            headers=self._auth(token),
        )

    # --- helpers --------------------------------------------------------

    @staticmethod
    def _auth(token: str) -> dict:
        # An empty token means "make an unauthenticated request", so send no
        # Authorization header at all. Sending "Bearer " with nothing after it
        # is an illegal HTTP header and would crash the client before the
        # request is even sent, rather than testing the build's behaviour.
        if not token:
            return {}
        return {"Authorization": f"Bearer {token}"}
