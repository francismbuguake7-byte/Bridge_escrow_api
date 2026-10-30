import uuid
from datetime import datetime
from extensions import db
from models.ledger import LedgerEntry

def get_user_balance(user_id):
    """
    Calculates the user's verified financial balances:
    - settled_balance: Funds cleared and released to the user
    - escrow_holding: Funds currently held in escrow (for buyer as active deposits, for seller as incoming sales in escrow)
    """
    credits = db.session.query(db.func.sum(LedgerEntry.amount)).filter_by(
        user_id=user_id, direction='credit', status='verified'
    ).scalar() or 0.0
    
    debits = db.session.query(db.func.sum(LedgerEntry.amount)).filter_by(
        user_id=user_id, direction='debit', status='verified'
    ).scalar() or 0.0
    
    return round(credits - debits, 2)

def record_ledger_entry(user_id, transaction_id, entry_type, amount, direction, description, provider='M-Pesa / Escrow Vault'):
    current_balance = get_user_balance(user_id)
    if direction == 'credit':
        new_balance = round(current_balance + amount, 2)
    else:
        new_balance = round(current_balance - amount, 2)
        
    ref = f"LED-{uuid.uuid4().hex[:10].upper()}"
    
    entry = LedgerEntry(
        user_id=user_id,
        transaction_id=transaction_id,
        entry_type=entry_type,
        amount=round(amount, 2),
        direction=direction,
        balance_after=new_balance,
        description=description,
        reference=ref,
        provider=provider,
        status='verified',
        created_at=datetime.utcnow()
    )
    db.session.add(entry)
    return entry
