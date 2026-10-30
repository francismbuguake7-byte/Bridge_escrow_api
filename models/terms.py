from datetime import datetime
from extensions import db

class TransactionTerms(db.Model):
    __tablename__ = 'transaction_terms'

    id = db.Column(db.Integer, primary_key=True)
    transaction_id = db.Column(db.Integer, db.ForeignKey('transactions.id'), nullable=False, unique=True)
    
    delivery_method = db.Column(db.String(50), nullable=False, default='courier')
    inspection_period_days = db.Column(db.Integer, nullable=False, default=3)
    acceptance_conditions = db.Column(db.Text, nullable=False)
    refund_conditions = db.Column(db.Text, nullable=False)
    release_requirements = db.Column(db.Text, nullable=False)
    
    buyer_accepted = db.Column(db.Boolean, default=False)
    seller_accepted = db.Column(db.Boolean, default=False)
    buyer_accepted_at = db.Column(db.DateTime, nullable=True)
    seller_accepted_at = db.Column(db.DateTime, nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'transaction_id': self.transaction_id,
            'delivery_method': self.delivery_method,
            'inspection_period_days': self.inspection_period_days,
            'acceptance_conditions': self.acceptance_conditions,
            'refund_conditions': self.refund_conditions,
            'release_requirements': self.release_requirements,
            'buyer_accepted': self.buyer_accepted,
            'seller_accepted': self.seller_accepted,
            'buyer_accepted_at': self.buyer_accepted_at.isoformat() if self.buyer_accepted_at else None,
            'seller_accepted_at': self.seller_accepted_at.isoformat() if self.seller_accepted_at else None,
            'fully_accepted': self.buyer_accepted and self.seller_accepted
        }
