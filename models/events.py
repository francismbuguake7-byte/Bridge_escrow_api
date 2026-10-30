import json
from datetime import datetime
from extensions import db

class DeliveryEvent(db.Model):
    __tablename__ = 'delivery_events'

    id = db.Column(db.Integer, primary_key=True)
    transaction_id = db.Column(db.Integer, db.ForeignKey('transactions.id'), nullable=False)
    event_type = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text, nullable=False)
    actor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    metadata_json = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationship to actor
    actor = db.relationship('User', foreign_keys=[actor_id], lazy=True)

    @classmethod
    def log(cls, transaction_id, event_type, description, actor_id=None, metadata=None):
        event = cls(
            transaction_id=transaction_id,
            event_type=event_type,
            description=description,
            actor_id=actor_id,
            metadata_json=json.dumps(metadata) if metadata else None
        )
        db.session.add(event)
        return event

    def to_dict(self):
        meta = None
        if self.metadata_json:
            try:
                meta = json.loads(self.metadata_json)
            except Exception:
                meta = {}
        return {
            'id': self.id,
            'transaction_id': self.transaction_id,
            'event_type': self.event_type,
            'description': self.description,
            'actor_id': self.actor_id,
            'actor_name': self.actor.full_name if self.actor else 'System',
            'metadata': meta,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
