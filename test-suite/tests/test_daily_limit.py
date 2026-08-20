"""
The rolling daily limit.

Covers BR3: the combined value of transfers and withdrawals by a user must not
exceed GBP 1,000 within any rolling 24-hour period; deposits do not count.

Note on scope: a test run happens within a single 24-hour window, so it can
verify the cumulative cap and what counts towards it, but it cannot verify that
the window resets after 24 hours without manipulating time. That aspect is
noted as a limitation rather than tested here.
"""

from conftest import assert_success, assert_rejected, balance
from api import DAILY_LIMIT_PENCE


def test_transfer_within_limit_allowed(api, funded_user, new_user):
    """BR3: transfers summing to just under the limit are allowed."""
    sender = funded_user(DAILY_LIMIT_PENCE * 3)
    recipient = new_user()

    r1 = api.transfer(sender.token, recipient.email, 60_000)
    r2 = api.transfer(sender.token, recipient.email, 30_000)
    assert_success(r1, 201)
    assert_success(r2, 201)  # 90,000 total, under 100,000


def test_transfer_over_limit_rejected(api, funded_user, new_user):
    """BR3: a transfer that would push the daily total over the limit is rejected."""
    sender = funded_user(DAILY_LIMIT_PENCE * 3)
    recipient = new_user()

    api.transfer(sender.token, recipient.email, 60_000)
    api.transfer(sender.token, recipient.email, 30_000)  # 90,000 so far

    over = api.transfer(sender.token, recipient.email, 20_000)  # would be 110,000
    assert_rejected(over)


def test_withdrawals_count_towards_limit(api, funded_user, new_user):
    """BR3: withdrawals and transfers share the same daily limit."""
    user = funded_user(DAILY_LIMIT_PENCE * 3)
    recipient = new_user()

    api.withdraw(user.token, 70_000)                       # 70,000 withdrawn
    over = api.transfer(user.token, recipient.email, 40_000)  # would be 110,000
    assert_rejected(over)


def test_deposits_do_not_count_towards_limit(api, funded_user, new_user):
    """BR3: deposits are exempt, so a large deposit does not block a later transfer."""
    sender = funded_user(DAILY_LIMIT_PENCE * 3)  # a large deposit
    recipient = new_user()

    # A modest transfer should still be allowed despite the big deposit.
    resp = api.transfer(sender.token, recipient.email, 50_000)
    assert_success(resp, 201)
