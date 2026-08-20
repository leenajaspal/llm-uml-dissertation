from datetime import datetime, timezone
from typing import List

import sqlite3
from fastapi import APIRouter, Depends, HTTPException

from dependencies import get_current_user, get_db
from schemas import (
    AmountRequest,
    ReversalResponse,
    TransactionResponse,
    TransactionResultResponse,
    TransferRequest,
)
from services import (
    DAILY_LIMIT_PENCE,
    compute_balance,
    daily_outflow_total,
    db_transaction,
    get_system_account,
    get_user_account,
    insert_ledger_entry,
    insert_transaction,
)

router = APIRouter(tags=["transactions"])


@router.post("/deposits", response_model=TransactionResultResponse, status_code=201)
def deposit(
    req: AmountRequest,
    user_id: int = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    acc = get_user_account(conn, user_id)
    sys_acc = get_system_account(conn)
    amount = req.amount_pence
    now_iso = datetime.now(timezone.utc).isoformat()

    with db_transaction(conn):
        tx_id = insert_transaction(conn, "deposit", "completed", now_iso)
        # Debit system account, credit user account (BR5)
        insert_ledger_entry(conn, tx_id, int(sys_acc["account_id"]), amount, "debit")
        insert_ledger_entry(conn, tx_id, int(acc["account_id"]), amount, "credit")

    balance = compute_balance(conn, int(acc["account_id"]))
    return TransactionResultResponse(
        transaction_id=tx_id, status="completed", balance_pence=balance
    )


@router.post("/withdrawals", response_model=TransactionResultResponse, status_code=201)
def withdraw(
    req: AmountRequest,
    user_id: int = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    acc = get_user_account(conn, user_id)
    sys_acc = get_system_account(conn)
    amount = req.amount_pence
    now = datetime.now(timezone.utc)

    with db_transaction(conn):
        balance = compute_balance(conn, int(acc["account_id"]))
        if balance < amount:
            raise HTTPException(status_code=422, detail="Insufficient funds")
        outflow = daily_outflow_total(conn, int(acc["account_id"]), now)
        if outflow + amount > DAILY_LIMIT_PENCE:
            raise HTTPException(
                status_code=422,
                detail="Daily limit exceeded for withdrawals and transfers",
            )
        tx_id = insert_transaction(conn, "withdrawal", "completed", now.isoformat())
        # Debit user account, credit system account (BR5)
        insert_ledger_entry(conn, tx_id, int(acc["account_id"]), amount, "debit")
        insert_ledger_entry(conn, tx_id, int(sys_acc["account_id"]), amount, "credit")

    balance = compute_balance(conn, int(acc["account_id"]))
    return TransactionResultResponse(
        transaction_id=tx_id, status="completed", balance_pence=balance
    )


@router.post("/transfers", response_model=TransactionResultResponse, status_code=201)
def transfer(
    req: TransferRequest,
    user_id: int = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    sender_acc = get_user_account(conn, user_id)
    amount = req.amount_pence
    recipient_email = req.recipient_email.strip().lower()
    now = datetime.now(timezone.utc)

    recipient_user = conn.execute(
        "SELECT user_id FROM users WHERE email = ?", (recipient_email,)
    ).fetchone()
    if recipient_user is None:
        raise HTTPException(status_code=404, detail="Recipient not found")
    if int(recipient_user["user_id"]) == user_id:
        raise HTTPException(
            status_code=422, detail="Cannot transfer funds to your own account"
        )
    recipient_acc = conn.execute(
        "SELECT * FROM accounts WHERE user_id = ?",
        (int(recipient_user["user_id"]),),
    ).fetchone()

    with db_transaction(conn):
        balance = compute_balance(conn, int(sender_acc["account_id"]))
        if balance < amount:
            raise HTTPException(status_code=422, detail="Insufficient funds")
        outflow = daily_outflow_total(conn, int(sender_acc["account_id"]), now)
        if outflow + amount > DAILY_LIMIT_PENCE:
            raise HTTPException(
                status_code=422,
                detail="Daily limit exceeded for withdrawals and transfers",
            )
        tx_id = insert_transaction(conn, "transfer", "completed", now.isoformat())
        # Debit sender, credit recipient
        insert_ledger_entry(conn, tx_id, int(sender_acc["account_id"]), amount, "debit")
        insert_ledger_entry(
            conn, tx_id, int(recipient_acc["account_id"]), amount, "credit"
        )

    balance = compute_balance(conn, int(sender_acc["account_id"]))
    return TransactionResultResponse(
        transaction_id=tx_id, status="completed", balance_pence=balance
    )


@router.get("/transactions", response_model=List[TransactionResponse], status_code=200)
def list_transactions(
    user_id: int = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    acc = get_user_account(conn, user_id)
    rows = conn.execute(
        """
        SELECT t.transaction_id, t.type, t.status, t.created_at,
               le.amount_pence, le.direction
        FROM transactions t
        JOIN ledger_entries le ON le.transaction_id = t.transaction_id
        WHERE le.account_id = ?
        ORDER BY t.created_at DESC, t.transaction_id DESC
        """,
        (int(acc["account_id"]),),
    ).fetchall()
    return [
        TransactionResponse(
            transaction_id=int(r["transaction_id"]),
            type=r["type"],
            amount_pence=int(r["amount_pence"]),
            direction=r["direction"],
            status=r["status"],
            created_at=r["created_at"],
        )
        for r in rows
    ]


@router.post(
    "/transactions/{transaction_id}/reversal",
    response_model=ReversalResponse,
    status_code=201,
)
def reverse_transfer(
    transaction_id: int,
    user_id: int = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    acc = get_user_account(conn, user_id)
    now_iso = datetime.now(timezone.utc).isoformat()

    with db_transaction(conn):
        orig = conn.execute(
            "SELECT * FROM transactions WHERE transaction_id = ?",
            (transaction_id,),
        ).fetchone()
        if orig is None:
            raise HTTPException(
                status_code=404, detail="Transaction not found"
            )
        if orig["type"] != "transfer":
            raise HTTPException(
                status_code=422, detail="Only transfers can be reversed"
            )
        if orig["status"] != "completed":
            raise HTTPException(
                status_code=422,
                detail="Transaction is not reversible (already reversed or not completed)",
            )

        entries = conn.execute(
            "SELECT * FROM ledger_entries WHERE transaction_id = ? "
            "ORDER BY ledger_entry_id",
            (transaction_id,),
        ).fetchall()
        if len(entries) != 2:
            raise HTTPException(
                status_code=500, detail="Corrupt transaction ledger"
            )

        user_entry = None
        other_entry = None
        for e in entries:
            if int(e["account_id"]) == int(acc["account_id"]):
                user_entry = e
            else:
                other_entry = e

        if user_entry is None:
            # User has no involvement in this transaction at all
            raise HTTPException(
                status_code=403, detail="Not authorized to reverse this transaction"
            )
        if user_entry["direction"] != "debit":
            # Only the sender (who was debited) may reverse
            raise HTTPException(
                status_code=403,
                detail="Only the sending party may reverse a transfer",
            )

        amount = int(user_entry["amount_pence"])
        sender_account_id = int(user_entry["account_id"])
        recipient_account_id = int(other_entry["account_id"])

        # New reversal transaction (BR7): opposite-direction entries
        reversal_tx_id = insert_transaction(
            conn,
            "reversal",
            "completed",
            now_iso,
            reverses_transaction_id=transaction_id,
        )
        # Original: debit sender / credit recipient
        # Reversal: debit recipient / credit sender
        insert_ledger_entry(
            conn, reversal_tx_id, recipient_account_id, amount, "debit"
        )
        insert_ledger_entry(
            conn, reversal_tx_id, sender_account_id, amount, "credit"
        )

        # Mark original as reversed (no entries are deleted or amended)
        conn.execute(
            "UPDATE transactions SET status = 'reversed' WHERE transaction_id = ?",
            (transaction_id,),
        )

    return ReversalResponse(
        transaction_id=reversal_tx_id,
        reverses_transaction_id=transaction_id,
        status="completed",
    )