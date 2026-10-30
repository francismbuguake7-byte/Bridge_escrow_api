from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db

class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    phone_number = db.Column(db.String(20), nullable=False, index=True)
    role = db.Column(db.String(20), nullable=False, default='buyer')  # buyer, seller, courier, admin
    kyc_status = db.Column(db.String(20), nullable=False, default='unverified')  # unverified, pending, verified
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    buyer_transactions = db.relationship('Transaction', foreign_keys='Transaction.buyer_id', backref='buyer', lazy=True)
    seller_transactions = db.relationship('Transaction', foreign_keys='Transaction.seller_id', backref='seller', lazy=True)
    courier_transactions = db.relationship('Transaction', foreign_keys='Transaction.courier_id', backref='courier', lazy=True)
    ledger_entries = db.relationship('LedgerEntry', backref='user', lazy=True)
    notifications = db.relationship('Notification', backref='user', lazy=True, order_by='Notification.created_at.desc()')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            'id': self.id,
            'email': self.email,
            'full_name': self.full_name,
            'phone_number': self.phone_number,
            'role': self.role,
            'kyc_status': self.kyc_status,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
