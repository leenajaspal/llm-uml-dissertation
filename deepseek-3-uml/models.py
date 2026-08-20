from database import get_db
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

class UserModel:
    @staticmethod
    def create(email: str, password_hash: str) -> int:
        with get_db() as conn:
            cursor = conn.execute(
                "INSERT INTO users (email, password_hash) VALUES (?, ?)",
                (email, password_hash)
            )
            user_id = cursor.lastrowid
            
            # Create account for the user
            conn.execute(
                "INSERT INTO accounts (user_id) VALUES (?)",
                (user_id,)
            )
            
            return user_id
    
    @staticmethod
    def get_by_email(email: str) -> Optional[Dict[str, Any]]:
        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE email = ?",
                (email,)
            ).fetchone()
            return dict(row) if row else None
    
    @staticmethod
    def get_by_id(user_id: int) -> Optional[Dict[str, Any]]:
        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE user_id = ?",
                (user_id,)
            ).fetchone()
            return dict(row) if row else None

class AccountModel:
    @staticmethod
    def get_by_user_id(user_id: int) -> Optional[Dict[str, Any]]:
        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM accounts WHERE user_id = ?",
                (user_id,)
            ).fetchone()
            return dict(row) if row else None
    
    @staticmethod
    def get_balance(account_id: int) -> int:
        """Calculate balance from ledger entries."""
        with get_db() as conn:
            result = conn.execute("""
                SELECT 
                    COALESCE(SUM(CASE WHEN direction = 'credit' THEN amount_pence ELSE -amount_pence END), 0) as balance
                FROM ledger_entries
                WHERE account_id = ?
            """, (account_id,)).fetchone()
            return result['balance']
    
    @staticmethod
    def get_system_account_id() -> int:
        return 0

class TransactionModel:
    @staticmethod
    def create_transaction(
        transaction_type: str,
        debit_account_id: int,
        credit_account_id: int,
        amount_pence: int,
        reverses_transaction_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Create a transaction with double-entry ledger entries atomically."""
        with get_db() as conn:
            # Create the transaction
            cursor = conn.execute(
                """INSERT INTO transactions (type, status, reverses_transaction_id)
                   VALUES (?, 'completed', ?)""",
                (transaction_type, reverses_transaction_id)
            )
            transaction_id = cursor.lastrowid
            
            # Create two ledger entries (debit and credit)
            conn.execute(
                """INSERT INTO ledger_entries (transaction_id, account_id, amount_pence, direction)
                   VALUES (?, ?, ?, 'debit')""",
                (transaction_id, debit_account_id, amount_pence)
            )
            
            conn.execute(
                """INSERT INTO ledger_entries (transaction_id, account_id, amount_pence, direction)
                   VALUES (?, ?, ?, 'credit')""",
                (transaction_id, credit_account_id, amount_pence)
            )
            
            return {
                'transaction_id': transaction_id,
                'type': transaction_type,
                'status': 'completed',
                'amount_pence': amount_pence
            }
    
    @staticmethod
    def get_by_id(transaction_id: int) -> Optional[Dict[str, Any]]:
        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM transactions WHERE transaction_id = ?",
                (transaction_id,)
            ).fetchone()
            return dict(row) if row else None
    
    @staticmethod
    def get_user_transactions(account_id: int) -> List[Dict[str, Any]]:
        with get_db() as conn:
            rows = conn.execute("""
                SELECT DISTINCT t.*, 
                    le.amount_pence,
                    le.direction,
                    CASE 
                        WHEN le.direction = 'credit' AND t.type = 'transfer' THEN 'incoming'
                        WHEN le.direction = 'debit' AND t.type = 'transfer' THEN 'outgoing'
                        WHEN t.type = 'deposit' THEN 'incoming'
                        WHEN t.type = 'withdrawal' THEN 'outgoing'
                        WHEN t.type = 'reversal' AND le.direction = 'credit' THEN 'incoming'
                        WHEN t.type = 'reversal' AND le.direction = 'debit' THEN 'outgoing'
                    END as transaction_direction
                FROM transactions t
                JOIN ledger_entries le ON t.transaction_id = le.transaction_id
                WHERE le.account_id = ?
                ORDER BY t.created_at DESC
            """, (account_id,)).fetchall()
            
            transactions = []
            for row in rows:
                tx_dict = dict(row)
                # Format the direction
                tx_dict['direction'] = tx_dict.pop('transaction_direction')
                transactions.append(tx_dict)
            
            return transactions
    
    @staticmethod
    def get_transfers_withdrawals_last_24h(account_id: int) -> int:
        """Get sum of transfers and withdrawals in last 24 hours."""
        with get_db() as conn:
            cutoff = datetime.utcnow() - timedelta(hours=24)
            result = conn.execute("""
                SELECT COALESCE(SUM(le.amount_pence), 0) as total
                FROM ledger_entries le
                JOIN transactions t ON le.transaction_id = t.transaction_id
                WHERE le.account_id = ?
                AND le.direction = 'debit'
                AND t.type IN ('withdrawal', 'transfer')
                AND t.status = 'completed'
                AND t.created_at >= ?
            """, (account_id, cutoff.isoformat())).fetchone()
            return result['total']
    
    @staticmethod
    def reverse_transfer(original_transaction_id: int, sender_account_id: int) -> Optional[Dict[str, Any]]:
        """Reverse a completed transfer."""
        with get_db() as conn:
            # Get the original transaction
            original = conn.execute(
                "SELECT * FROM transactions WHERE transaction_id = ? AND type = 'transfer' AND status = 'completed'",
                (original_transaction_id,)
            ).fetchone()
            
            if not original:
                return None
            
            # Check if already reversed
            already_reversed = conn.execute(
                "SELECT COUNT(*) as count FROM transactions WHERE reverses_transaction_id = ?",
                (original_transaction_id,)
            ).fetchone()['count']
            
            if already_reversed > 0:
                return None
            
            # Get the original ledger entries
            entries = conn.execute(
                "SELECT * FROM ledger_entries WHERE transaction_id = ?",
                (original_transaction_id,)
            ).fetchall()
            
            # Find the debit entry (sender's side) and credit entry (recipient's side)
            debit_entry = next((e for e in entries if e['direction'] == 'debit'), None)
            credit_entry = next((e for e in entries if e['direction'] == 'credit'), None)
            
            if not debit_entry or not credit_entry:
                return None
            
            # Verify the requester is the original sender
            if debit_entry['account_id'] != sender_account_id:
                return None
            
            amount_pence = debit_entry['amount_pence']
            recipient_account_id = credit_entry['account_id']
            system_account_id = AccountModel.get_system_account_id()
            
            # Create reversal transaction (credit sender, debit recipient)
            cursor = conn.execute(
                """INSERT INTO transactions (type, status, reverses_transaction_id)
                   VALUES ('reversal', 'completed', ?)""",
                (original_transaction_id,)
            )
            reversal_id = cursor.lastrowid
            
            # Reverse the entries: credit the sender, debit the recipient
            conn.execute(
                """INSERT INTO ledger_entries (transaction_id, account_id, amount_pence, direction)
                   VALUES (?, ?, ?, 'credit')""",
                (reversal_id, sender_account_id, amount_pence)
            )
            
            conn.execute(
                """INSERT INTO ledger_entries (transaction_id, account_id, amount_pence, direction)
                   VALUES (?, ?, ?, 'debit')""",
                (reversal_id, recipient_account_id, amount_pence)
            )
            
            # Mark original as reversed
            conn.execute(
                "UPDATE transactions SET status = 'reversed' WHERE transaction_id = ?",
                (original_transaction_id,)
            )
            
            return {
                'transaction_id': reversal_id,
                'reverses_transaction_id': original_transaction_id,
                'status': 'completed',
                'amount_pence': amount_pence
            }