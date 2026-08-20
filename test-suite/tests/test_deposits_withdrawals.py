"""
Depositing, withdrawing, and viewing balance.

Covers FR3, FR4, FR5, and BR2.
"""

from conftest import assert_success, assert_rejected, balance


def test_new_account_starts_empty(api, new_user):
    """FR3: a newly registered user can view a balance, and it starts at zero."""
    user = new_user()
    assert balance(api, user) == 0


def test_deposit_increases_balance(api, new_user):
    """FR4: a deposit adds funds to the user's own account."""
    user = new_user()
    resp = api.deposit(user.token, 5000)
    assert_success(resp, 201)
    assert balance(api, user) == 5000


def test_multiple_deposits_accumulate(api, new_user):
    """FR4: successive deposits add up."""
    user = new_user()
    api.deposit(user.token, 5000)
    api.deposit(user.token, 2500)
    assert balance(api, user) == 7500


def test_withdrawal_decreases_balance(api, funded_user):
    """FR5: a withdrawal removes funds from the user's own account."""
    user = funded_user(5000)
    resp = api.withdraw(user.token, 2000)
    assert_success(resp, 201)
    assert balance(api, user) == 3000


def test_withdrawal_rejected_when_insufficient(api, funded_user):
    """BR2: a withdrawal larger than the balance is rejected, and nothing moves."""
    user = funded_user(1000)
    before = balance(api, user)
    resp = api.withdraw(user.token, 5000)
    assert_rejected(resp)
    assert balance(api, user) == before


def test_full_balance_can_be_withdrawn(api, funded_user):
    """FR5: withdrawing exactly the balance is allowed and leaves zero."""
    user = funded_user(3000)
    resp = api.withdraw(user.token, 3000)
    assert_success(resp, 201)
    assert balance(api, user) == 0
