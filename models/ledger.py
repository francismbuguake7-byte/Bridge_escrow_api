from datetime import datetime
from extensions import db

class LedgerEntry(db.Model):
    __tablename__ = 'ledger_entries'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    transaction_id = db.Column(db.Integer, db.ForeignKey('transactions.id'), nullable=True)
    
    entry_type = db.Column(db.String(30), nullable=False)
    # escrow_deposit: buyer paid funds into vault
    # escrow_hold: funds locked in escrow protection
    # escrow_release: funds released to seller upon inspection acceptance
    # platform_fee: platform fee deducted
    # buyer_refund: refund released back to buyer
    # settlement_payout: settlement to user account/mpesa
    
    amount = db.Column(db.Float, nullable=False)
    direction = db.Column(db.String(10), nullable=False)  # 'credit' (funds added) or 'debit' (funds deducted)
    balance_after = db.Column(db.Float, nullable=False, default=0.0)
    
    description = db.Column(db.String(255), nullable=False)
    reference = db.Column(db.String(64), nullable=False, index=True)
    provider = db.Column(db.String(30), nullable=False, default='M-Pesa / Escrow Vault')
    status = db.Column(db.String(20), nullable=False, default='verified')  # verified, pending, reversed
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'transaction_id': self.transaction_id,
            'entry_type': self.entry_type,
            'amount': self.amount,
            'direction': self.direction,
            'balance_after': self.balance_after,
            'description': self.description,
            'reference': self.reference,
            'provider': self.provider,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
