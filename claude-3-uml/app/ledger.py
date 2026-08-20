"""Double-entry ledger and the operations built on top of it.

Invariants
----------
* Every transaction writes exactly two ledger entries: one debit and one
  credit, of equal value, against two *different* accounts. The signed sum of
  all ledger entries is therefore always zero (BR4).
* An account's balance is the signed sum of its own ledger entries
  (credit = +, debit = -). It is derived on demand, never stored (BR6).
* Nothing is ever deleted or amended, except that reversing a transfer flips
  the original transaction's ``status`` to ``reversed`` (BR7).

Every public operation here must be called inside
:func:`app.db.write_transaction` so that the balance/limit checks and the
ledger writes happen as one atomic, serialised unit (NFR5).
"""

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Optional

from .config import DAILY_LIMIT_PENCE, DAILY_WINDOW_SECONDS
from .db import system_account_id
from .security import now_iso


class WalletError(Exception):
    """A domain-level rejection, carrying the HTTP status to return."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


# --------------------------------------------------------------------------- #
# Lookups
# --------------------------------------------------------------------------- #
def user_account_id(conn: sqlite3.Connection, user_id: int) -> int:
    row = conn.execute(
        "SELECT account_id FROM accounts WHERE user_id = ?", (user_id,)
    ).fetchone()
    if row is None:  # pragma: no cover - every user has an account
        raise WalletError(404, "account not found")
    return int(row["account_id"])


def find_user_by_email(conn: sqlite3.Connection, email: str) -> Optional[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM users WHERE email = ?", (email.lower(),)
    ).fetchone()


# --------------------------------------------------------------------------- #
# Derived quantities
# --------------------------------------------------------------------------- #
def account_balance(conn: sqlite3.Connection, account_id: int) -> int:
    """Balance of an account, derived from its ledger entries (BR6)."""
    row = conn.execute(
        """
        SELECT COALESCE(SUM(
            CASE direction WHEN 'credit' THEN amount_pence ELSE -amount_pence END
        ), 0) AS balance
        FROM ledger_entries
        WHERE account_id = ?
        """,
        (account_id,),
    ).fetchone()
    return int(row["balance"])


def outflow_last_24h(conn: sqlite3.Connection, account_id: int) -> int:
    """Sum of the user's outgoing transfers and withdrawals in the rolling
    24-hour window ending now (BR3). Deposits and reversals are excluded.

    An outgoing transfer/withdrawal is a *debit* against the user's account for
    a transaction of type ``transfer`` or ``withdrawal``. Reversed transfers are
    still counted: BR3 limits the value a user *sends out* in the window, and a
    later corrective reversal does not restore that day's allowance.
    """
    window_start = (
        datetime.now(timezone.utc) - timedelta(seconds=DAILY_WINDOW_SECONDS)
    ).isoformat()
    row = conn.execute(
        """
        SELECT COALESCE(SUM(le.amount_pence), 0) AS total
        FROM ledger_entries le
        JOIN transactions t ON t.transaction_id = le.transaction_id
        WHERE le.account_id = ?
          AND le.direction = 'debit'
          AND t.type IN ('transfer', 'withdrawal')
          AND t.created_at >= ?
        """,
        (account_id, window_start),
    ).fetchone()
    return int(row["total"])


# --------------------------------------------------------------------------- #
# Writing transactions
# --------------------------------------------------------------------------- #
def _post_transaction(
    conn: sqlite3.Connection,
    *,
    ttype: str,
    debit_account: int,
    credit_account: int,
    amount_pence: int,
    reverses_transaction_id: Optional[int] = None,
) -> int:
    """Insert one transaction and its two balancing ledger entries.

    Must be called within an active write transaction.
    """
    if debit_account == credit_account:  # pragma: no cover - guarded by callers
        raise WalletError(422, "a transaction must involve two different accounts")

    cur = conn.execute(
        "INSERT INTO transactions (type, status, created_at, reverses_transaction_id) "
        "VALUES (?, 'completed', ?, ?)",
        (ttype, now_iso(), reverses_transaction_id),
    )
    transaction_id = int(cur.lastrowid)

    conn.execute(
        "INSERT INTO ledger_entries (transaction_id, account_id, amount_pence, direction) "
        "VALUES (?, ?, ?, 'debit')",
        (transaction_id, debit_account, amount_pence),
    )
    conn.execute(
        "INSERT INTO ledger_entries (transaction_id, account_id, amount_pence, direction) "
        "VALUES (?, ?, ?, 'credit')",
        (transaction_id, credit_account, amount_pence),
    )
    return transaction_id


# --------------------------------------------------------------------------- #
# Operations (each opens its own atomic write transaction)
# --------------------------------------------------------------------------- #
def deposit(conn: sqlite3.Connection, user_id: int, amount_pence: int) -> dict:
    """FR4/BR5: debit the system account, credit the user's account."""
    from .db import write_transaction

    with write_transaction(conn):
        account = user_account_id(conn, user_id)
        system = system_account_id(conn)
        txn_id = _post_transaction(
            conn,
            ttype="deposit",
            debit_account=system,
            credit_account=account,
            amount_pence=amount_pence,
        )
        balance = account_balance(conn, account)
    return {"transaction_id": txn_id, "status": "completed", "balance_pence": balance}


def withdraw(conn: sqlite3.Connection, user_id: int, amount_pence: int) -> dict:
    """FR5/BR5: debit the user's account, credit the system account.

    Rejected if the balance is insufficient (BR2) or the daily limit would be
    exceeded (BR3).
    """
    from .db import write_transaction

    with write_transaction(conn):
        account = user_account_id(conn, user_id)
        system = system_account_id(conn)

        balance = account_balance(conn, account)
        if balance < amount_pence:
            raise WalletError(422, "insufficient funds")

        already_out = outflow_last_24h(conn, account)
        if already_out + amount_pence > DAILY_LIMIT_PENCE:
            raise WalletError(422, "daily transfer/withdrawal limit exceeded")

        txn_id = _post_transaction(
            conn,
            ttype="withdrawal",
            debit_account=account,
            credit_account=system,
            amount_pence=amount_pence,
        )
        new_balance = account_balance(conn, account)
    return {
        "transaction_id": txn_id,
        "status": "completed",
        "balance_pence": new_balance,
    }


def transfer(
    conn: sqlite3.Connection,
    user_id: int,
    recipient_email: str,
    amount_pence: int,
) -> dict:
    """FR6: debit the sender, credit the recipient.

    Rejections: unknown recipient (BR10), self-transfer (BR9), insufficient
    funds (BR1), daily limit exceeded (BR3).
    """
    from .db import write_transaction

    with write_transaction(conn):
        sender_account = user_account_id(conn, user_id)

        recipient = find_user_by_email(conn, recipient_email)
        if recipient is None:
            raise WalletError(404, "recipient is not a registered user")
        if int(recipient["user_id"]) == user_id:
            raise WalletError(422, "cannot transfer to your own account")

        recipient_account = user_account_id(conn, int(recipient["user_id"]))

        balance = account_balance(conn, sender_account)
        if balance < amount_pence:
            raise WalletError(422, "insufficient funds")

        already_out = outflow_last_24h(conn, sender_account)
        if already_out + amount_pence > DAILY_LIMIT_PENCE:
            raise WalletError(422, "daily transfer/withdrawal limit exceeded")

        txn_id = _post_transaction(
            conn,
            ttype="transfer",
            debit_account=sender_account,
            credit_account=recipient_account,
            amount_pence=amount_pence,
        )
        new_balance = account_balance(conn, sender_account)
    return {
        "transaction_id": txn_id,
        "status": "completed",
        "balance_pence": new_balance,
    }


def reverse_transfer(
    conn: sqlite3.Connection, user_id: int, transaction_id: int
) -> dict:
    """FR8: reverse a completed transfer in which the caller was the sender.

    A new ``reversal`` transaction is created with the value moved in the
    opposite direction, and the original is marked ``reversed`` (BR7). The
    original is untouched otherwise; ledger entries are never deleted or amended.

    Only a *completed transfer* may be reversed, and only once (BR8).
    """
    from .db import write_transaction

    with write_transaction(conn):
        txn = conn.execute(
            "SELECT * FROM transactions WHERE transaction_id = ?",
            (transaction_id,),
        ).fetchone()
        if txn is None:
            raise WalletError(404, "transaction not found")

        entries = conn.execute(
            "SELECT account_id, amount_pence, direction "
            "FROM ledger_entries WHERE transaction_id = ?",
            (transaction_id,),
        ).fetchall()
        debit_entry = next(e for e in entries if e["direction"] == "debit")
        credit_entry = next(e for e in entries if e["direction"] == "credit")
        sender_account = int(debit_entry["account_id"])
        recipient_account = int(credit_entry["account_id"])
        amount_pence = int(debit_entry["amount_pence"])

        my_account = user_account_id(conn, user_id)

        # NFR3: a transaction the caller is not a party to is not visible.
        if my_account not in (sender_account, recipient_account):
            raise WalletError(404, "transaction not found")

        # BR8: only transfers are reversible.
        if txn["type"] != "transfer":
            raise WalletError(409, "only completed transfers can be reversed")

        # FR8: only the sending party may reverse.
        if my_account != sender_account:
            raise WalletError(403, "only the sender may reverse this transfer")

        # BR8: a transfer can only be reversed once (and must be completed).
        if txn["status"] != "completed":
            raise WalletError(409, "transfer has already been reversed")

        reversal_id = _post_transaction(
            conn,
            ttype="reversal",
            debit_account=recipient_account,   # opposite direction (BR7)
            credit_account=sender_account,
            amount_pence=amount_pence,
            reverses_transaction_id=transaction_id,
        )
        conn.execute(
            "UPDATE transactions SET status = 'reversed' WHERE transaction_id = ?",
            (transaction_id,),
        )

    return {
        "transaction_id": reversal_id,
        "reverses_transaction_id": transaction_id,
        "status": "completed",
    }


# --------------------------------------------------------------------------- #
# Queries
# --------------------------------------------------------------------------- #
def list_transactions(conn: sqlite3.Connection, user_id: int) -> list:
    """FR7: the caller's own transaction history, newest first.

    Each transaction that touches the user's account has exactly one ledger
    entry on that account; ``amount_pence`` and ``direction`` are taken from
    that entry, so they reflect the transaction from the user's perspective.
    """
    account = user_account_id(conn, user_id)
    rows = conn.execute(
        """
        SELECT t.transaction_id AS transaction_id,
               t.type           AS type,
               le.amount_pence  AS amount_pence,
               le.direction     AS direction,
               t.status         AS status,
               t.created_at     AS created_at
        FROM transactions t
        JOIN ledger_entries le ON le.transaction_id = t.transaction_id
        WHERE le.account_id = ?
        ORDER BY t.created_at DESC, t.transaction_id DESC
        """,
        (account,),
    ).fetchall()
    return [dict(r) for r in rows]
