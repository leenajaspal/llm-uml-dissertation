# Test inventory

Every test in the suite, grouped by area, with the requirement or business rule
it checks. 45 tests in total (the validation tests each run against four bad
inputs, which is why the counts below sum to more than the number of test
functions).

This table is suitable for the appendix. It also shows the coverage of the
requirements at a glance, and which requirements are checked by other evaluation
dimensions rather than by this suite.

## Authentication (`test_auth.py`)

| Test | Checks |
|---|---|
| Register a new user | FR1 |
| Registration does not return the password | NFR1 (partial) |
| Reject duplicate email | FR1 (unique email) |
| Login returns a token | FR2 |
| Login rejects wrong password | FR2 |
| Login rejects unknown user | FR2 |
| Balance requires authentication | NFR2 |
| Deposit requires authentication | NFR2 |
| Invalid token is rejected | NFR2 |

## Deposits and withdrawals (`test_deposits_withdrawals.py`)

| Test | Checks |
|---|---|
| New account starts at zero | FR3 |
| Deposit increases balance | FR4 |
| Multiple deposits accumulate | FR4 |
| Withdrawal decreases balance | FR5 |
| Withdrawal rejected when insufficient | BR2 |
| Full balance can be withdrawn | FR5 |

## Transfers (`test_transfers.py`)

| Test | Checks |
|---|---|
| Transfer moves money | FR6 |
| Transfer conserves money (sender + recipient total unchanged) | BR4 (black-box proxy) |
| Transfer rejected when insufficient | BR1 |
| Transfer to self rejected | BR9 |
| Transfer to unknown recipient rejected | BR10 |
| Transfer requires authentication | NFR2 |

## Daily limit (`test_daily_limit.py`)

| Test | Checks |
|---|---|
| Transfers within the limit are allowed | BR3 |
| Transfer over the limit is rejected | BR3 |
| Withdrawals count towards the limit | BR3 |
| Deposits do not count towards the limit | BR3 |

## Transaction history and isolation (`test_transactions.py`)

| Test | Checks |
|---|---|
| History lists the user's own transactions | FR7 |
| History requires authentication | NFR2 |
| A user cannot see another user's transactions | NFR3 |

## Reversal (`test_reversal.py`)

| Test | Checks |
|---|---|
| Reversal returns money to both sides | FR8, BR7 |
| Reversal preserves the original transaction | BR7 |
| A transfer cannot be reversed twice | BR8 |
| A deposit cannot be reversed | BR8 |
| A user cannot reverse another user's transfer | NFR3, BR8 |

## Monetary input validation (`test_validation.py`)

Each of these runs against four bad inputs: zero, negative, fractional, and a
non-numeric string.

| Test | Checks |
|---|---|
| Deposit rejects bad amount (×4) | BR11, NFR4 |
| Withdrawal rejects bad amount (×4) | BR11, NFR4 |
| Transfer rejects bad amount (×4) | BR11, NFR4 |

## Requirement coverage summary

| Requirement | Covered by this suite? |
|---|---|
| FR1–FR8 (all functions) | Yes |
| BR1 insufficient funds (transfer) | Yes |
| BR2 insufficient funds (withdrawal) | Yes |
| BR3 rolling daily limit | Cumulative cap yes; 24-hour reset no (needs time control) |
| BR4 double-entry balancing | Black-box proxy only (money conserved) |
| BR5 system account counterparty | Indirect (deposit/withdraw effects) |
| BR6 balance derived from ledger | Not black-box testable; static / manual review |
| BR7 reversal is compensating, original preserved | Yes |
| BR8 only completed transfers, only once | Yes |
| BR9 no self-transfer | Yes |
| BR10 unknown recipient rejected | Yes |
| BR11 valid amounts | Yes |
| NFR1 password hashing | Partial (never echoed); storage via manual review |
| NFR2 authentication required | Yes |
| NFR3 data isolation | Yes |
| NFR4 input validation | Yes |
| NFR5 atomic ledger writes | Not black-box testable; static / manual review |

The requirements marked as not black-box testable are deliberately left to the
code-quality, security, and hallucination dimensions, which inspect the code
itself rather than its behaviour over HTTP.
