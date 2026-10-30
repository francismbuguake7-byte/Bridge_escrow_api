import json
from datetime import datetime
from extensions import db

class AuditLog(db.Model):
    __tablename__ = 'audit_logs'

    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    action = db.Column(db.String(100), nullable=False)
    target_type = db.Column(db.String(50), nullable=False)
    target_id = db.Column(db.Integer, nullable=True)
    details_json = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    actor = db.relationship('User', foreign_keys=[actor_id], lazy=True)

    @classmethod
    def record(cls, action, target_type, target_id=None, actor_id=None, details=None, ip_address=None):
        log = cls(
            action=action,
            target_type=target_type,
            target_id=target_id,
            actor_id=actor_id,
            details_json=json.dumps(details) if details else None,
            ip_address=ip_address
        )
        db.session.add(log)
        return log

    def to_dict(self):
        details = {}
        if self.details_json:
            try:
                details = json.loads(self.details_json)
            except Exception:
                details = {}
        return {
            'id': self.id,
            'actor_id': self.actor_id,
            'actor_name': self.actor.full_name if self.actor else 'System',
            'action': self.action,
            'target_type': self.target_type,
            'target_id': self.target_id,
            'details': details,
            'ip_address': self.ip_address,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
