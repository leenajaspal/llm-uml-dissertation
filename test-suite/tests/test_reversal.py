"""
Reversing a transfer.

Covers FR8, BR7 (reversal is a new compensating transaction, the original is
preserved), BR8 (only a completed transfer, only once, and only transfers),
and the NFR3 case of reversing someone else's transaction.
"""

from conftest import assert_success, assert_rejected, balance


def _make_transfer(api, sender, recipient, amount):
    resp = api.transfer(sender.token, recipient.email, amount)
    assert_success(resp, 201)
    return resp.json()["transaction_id"]


def test_reversal_returns_money(api, funded_user, new_user):
    """FR8 / BR7: reversing a transfer puts the money back on both sides."""
    sender = funded_user(5000)
    recipient = new_user()
    txn_id = _make_transfer(api, sender, recipient, 2000)

    # After the transfer: sender 3000, recipient 2000.
    resp = api.reversal(sender.token, txn_id)
    assert_success(resp, 201)

    assert balance(api, sender) == 5000
    assert balance(api, recipient) == 0


def test_reversal_preserves_original(api, funded_user, new_user):
    """
    BR7: the original transfer is not deleted. After a reversal the history
    still contains the original transaction as well as the reversal.
    """
    sender = funded_user(5000)
    recipient = new_user()
    txn_id = _make_transfer(api, sender, recipient, 2000)
    api.reversal(sender.token, txn_id)

    resp = api.transactions(sender.token)
    assert_success(resp, 200)
    body = resp.json()
    txns = body["transactions"] if isinstance(body, dict) else body
    ids = [t.get("transaction_id") for t in txns]

    # The original transfer id is still present in the history.
    assert txn_id in ids


def test_transfer_cannot_be_reversed_twice(api, funded_user, new_user):
    """BR8: a transfer may be reversed only once."""
    sender = funded_user(5000)
    recipient = new_user()
    txn_id = _make_transfer(api, sender, recipient, 2000)

    first = api.reversal(sender.token, txn_id)
    assert_success(first, 201)

    second = api.reversal(sender.token, txn_id)
    assert_rejected(second)


def test_deposit_cannot_be_reversed(api, new_user):
    """BR8: only transfers are reversible; a deposit is not."""
    user = new_user()
    resp = api.deposit(user.token, 5000)
    assert_success(resp, 201)
    deposit_id = resp.json()["transaction_id"]

    rev = api.reversal(user.token, deposit_id)
    assert_rejected(rev)


def test_cannot_reverse_another_users_transfer(api, funded_user, new_user):
    """
    NFR3 / BR8: a user cannot reverse a transfer they did not make.

    Alice transfers to Bob. Bob (or anyone who is not the sender) must not be
    able to reverse Alice's transfer.
    """
    alice = funded_user(5000)
    bob = new_user()
    txn_id = _make_transfer(api, alice, bob, 2000)

    rev = api.reversal(bob.token, txn_id)
    assert_rejected(rev)
