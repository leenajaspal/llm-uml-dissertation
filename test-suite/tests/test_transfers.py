"""
Transferring money between users.

Covers FR6, BR1, BR9, BR10, and a black-box check of BR4 (money is neither
created nor destroyed by a transfer).
"""

from conftest import assert_success, assert_rejected, balance
from api import unique_email


def test_transfer_moves_money(api, funded_user, new_user):
    """FR6: an authenticated user transfers funds to another registered user."""
    sender = funded_user(5000)
    recipient = new_user()

    resp = api.transfer(sender.token, recipient.email, 2000)
    assert_success(resp, 201)

    assert balance(api, sender) == 3000
    assert balance(api, recipient) == 2000


def test_transfer_conserves_money(api, funded_user, new_user):
    """
    BR4 (black box): the total held by sender and recipient together is
    unchanged by a transfer. Money moves, it is not created or destroyed.
    """
    sender = funded_user(5000)
    recipient = new_user()

    total_before = balance(api, sender) + balance(api, recipient)
    api.transfer(sender.token, recipient.email, 1500)
    total_after = balance(api, sender) + balance(api, recipient)

    assert total_before == total_after


def test_transfer_rejected_when_insufficient(api, funded_user, new_user):
    """BR1: a transfer larger than the sender's balance is rejected, nothing moves."""
    sender = funded_user(1000)
    recipient = new_user()

    s_before = balance(api, sender)
    r_before = balance(api, recipient)

    resp = api.transfer(sender.token, recipient.email, 5000)
    assert_rejected(resp)

    assert balance(api, sender) == s_before
    assert balance(api, recipient) == r_before


def test_transfer_to_self_rejected(api, funded_user):
    """BR9: a user cannot transfer to their own account."""
    user = funded_user(5000)
    before = balance(api, user)
    resp = api.transfer(user.token, user.email, 1000)
    assert_rejected(resp)
    assert balance(api, user) == before


def test_transfer_to_unknown_recipient_rejected(api, funded_user):
    """BR10: a transfer to an unregistered address is rejected, nothing moves."""
    sender = funded_user(5000)
    before = balance(api, sender)
    resp = api.transfer(sender.token, unique_email(), 1000)
    assert_rejected(resp)
    assert balance(api, sender) == before


def test_transfer_requires_authentication(api, new_user):
    """NFR2: a transfer with no credential is rejected."""
    recipient = new_user()
    resp = api.transfer("", recipient.email, 1000)
    assert_rejected(resp)
