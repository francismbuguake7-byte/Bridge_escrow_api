import json
from datetime import datetime
from extensions import db

class Dispute(db.Model):
    __tablename__ = 'disputes'

    id = db.Column(db.Integer, primary_key=True)
    transaction_id = db.Column(db.Integer, db.ForeignKey('transactions.id'), nullable=False)
    initiator_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    reason = db.Column(db.String(100), nullable=False)
    # damaged_goods, not_as_described, missing_items, non_delivery, incomplete_service, unauthorized_terms
    description = db.Column(db.Text, nullable=False)
    evidence_urls = db.Column(db.Text, nullable=True)  # JSON list of urls/docs
    
    status = db.Column(db.String(30), nullable=False, default='open')
    # open, under_review, resolved_buyer_refund, resolved_seller_payout, resolved_split, rejected
    
    resolution = db.Column(db.String(50), nullable=True)
    resolution_notes = db.Column(db.Text, nullable=True)
    resolved_by_admin_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    resolved_at = db.Column(db.DateTime, nullable=True)

    initiator = db.relationship('User', foreign_keys=[initiator_id], lazy=True)
    resolved_by_admin = db.relationship('User', foreign_keys=[resolved_by_admin_id], lazy=True)

    def to_dict(self):
        evidences = []
        if self.evidence_urls:
            try:
                evidences = json.loads(self.evidence_urls)
            except Exception:
                evidences = []
        return {
            'id': self.id,
            'transaction_id': self.transaction_id,
            'initiator_id': self.initiator_id,
            'initiator_name': self.initiator.full_name if self.initiator else None,
            'reason': self.reason,
            'description': self.description,
            'evidence_urls': evidences,
            'status': self.status,
            'resolution': self.resolution,
            'resolution_notes': self.resolution_notes,
            'resolved_by_admin_id': self.resolved_by_admin_id,
            'resolved_by_admin_name': self.resolved_by_admin.full_name if self.resolved_by_admin else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'resolved_at': self.resolved_at.isoformat() if self.resolved_at else None
        }
