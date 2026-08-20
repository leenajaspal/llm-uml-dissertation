"""
Validation of monetary input.

Covers BR11 and NFR4: deposit, withdrawal and transfer amounts must be positive
whole numbers of pence. Zero, negative, fractional and non-numeric amounts are
rejected without changing any account.

Each rejection is confirmed both by a non-success response and by the balance
being unchanged, so a build that quietly accepts a bad amount is caught even if
it returns a misleading status.
"""

import pytest
from conftest import assert_rejected, balance


BAD_AMOUNTS = [
    pytest.param(0, id="zero"),
    pytest.param(-100, id="negative"),
    pytest.param(10.5, id="fractional"),
    pytest.param("abc", id="non_numeric_string"),
]


@pytest.mark.parametrize("amount", BAD_AMOUNTS)
def test_deposit_rejects_bad_amount(api, new_user, amount):
    """BR11 / NFR4: invalid deposit amounts are rejected and nothing changes."""
    user = new_user()
    before = balance(api, user)
    resp = api.deposit(user.token, amount)
    assert_rejected(resp)
    assert balance(api, user) == before


@pytest.mark.parametrize("amount", BAD_AMOUNTS)
def test_withdrawal_rejects_bad_amount(api, funded_user, amount):
    """BR11 / NFR4: invalid withdrawal amounts are rejected and nothing changes."""
    user = funded_user(5000)
    before = balance(api, user)
    resp = api.withdraw(user.token, amount)
    assert_rejected(resp)
    assert balance(api, user) == before


@pytest.mark.parametrize("amount", BAD_AMOUNTS)
def test_transfer_rejects_bad_amount(api, funded_user, new_user, amount):
    """BR11 / NFR4: invalid transfer amounts are rejected and nothing changes."""
    sender = funded_user(5000)
    recipient = new_user()
    before = balance(api, sender)
    resp = api.transfer(sender.token, recipient.email, amount)
    assert_rejected(resp)
    assert balance(api, sender) == before
