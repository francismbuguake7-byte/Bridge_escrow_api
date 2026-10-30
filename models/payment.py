from datetime import datetime
from extensions import db

class Payment(db.Model):
    __tablename__ = 'payments'

    id = db.Column(db.Integer, primary_key=True)
    transaction_id = db.Column(db.Integer, db.ForeignKey('transactions.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(5), nullable=False, default='KES')
    provider = db.Column(db.String(20), nullable=False, default='mpesa')  # mpesa, card, simulated
    
    checkout_request_id = db.Column(db.String(100), unique=True, nullable=True, index=True)
    merchant_request_id = db.Column(db.String(100), nullable=True)
    mpesa_receipt_number = db.Column(db.String(50), nullable=True, index=True)
    phone_number = db.Column(db.String(20), nullable=False)
    
    status = db.Column(db.String(20), nullable=False, default='pending')  # pending, completed, failed, refunded
    failure_reason = db.Column(db.String(255), nullable=True)
    raw_callback = db.Column(db.Text, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'transaction_id': self.transaction_id,
            'user_id': self.user_id,
            'amount': self.amount,
            'currency': self.currency,
            'provider': self.provider,
            'checkout_request_id': self.checkout_request_id,
            'mpesa_receipt_number': self.mpesa_receipt_number,
            'phone_number': self.phone_number,
            'status': self.status,
            'failure_reason': self.failure_reason,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None
        }
