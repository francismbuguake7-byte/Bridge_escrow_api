import hashlib
import secrets
from datetime import datetime, timedelta
from extensions import db

class VerificationCode(db.Model):
    __tablename__ = 'verification_codes'

    id = db.Column(db.Integer, primary_key=True)
    transaction_id = db.Column(db.Integer, db.ForeignKey('transactions.id'), nullable=False)
    
    code_type = db.Column(db.String(20), nullable=False)  # 'pickup' or 'handover'
    code_hash = db.Column(db.String(128), nullable=False)
    salt = db.Column(db.String(32), nullable=False)
    
    attempts = db.Column(db.Integer, nullable=False, default=0)
    max_attempts = db.Column(db.Integer, nullable=False, default=3)
    
    expires_at = db.Column(db.DateTime, nullable=False)
    is_used = db.Column(db.Boolean, nullable=False, default=False)
    used_at = db.Column(db.DateTime, nullable=True)
    used_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @staticmethod
    def hash_code(code_str, salt):
        return hashlib.sha256(f"{salt}:{code_str}".encode('utf-8')).hexdigest()

    @classmethod
    def generate_code(cls, transaction_id, code_type, expiry_hours=48):
        # 6-digit numeric secure code
        raw_code = f"{secrets.randbelow(900000) + 100000}"
        salt = secrets.token_hex(16)
        code_hash = cls.hash_code(raw_code, salt)
        expires_at = datetime.utcnow() + timedelta(hours=expiry_hours)
        
        # Invalidate any unused prior code for same transaction & type
        cls.query.filter_by(transaction_id=transaction_id, code_type=code_type, is_used=False).delete()
        
        instance = cls(
            transaction_id=transaction_id,
            code_type=code_type,
            code_hash=code_hash,
            salt=salt,
            expires_at=expires_at,
            attempts=0,
            max_attempts=3,
            is_used=False
        )
        db.session.add(instance)
        # Note: Return the raw_code to caller once for display to authorized party
        return instance, raw_code

    def verify(self, code_str, user_id):
        if self.is_used:
            return False, "This verification code has already been used."
        
        if datetime.utcnow() > self.expires_at:
            return False, "This verification code has expired."
            
        if self.attempts >= self.max_attempts:
            return False, "Maximum verification attempts exceeded. Code is locked."
            
        self.attempts += 1
        computed_hash = self.hash_code(code_str.strip(), self.salt)
        
        if computed_hash == self.code_hash:
            self.is_used = True
            self.used_at = datetime.utcnow()
            self.used_by_user_id = user_id
            db.session.commit()
            return True, "Code successfully verified."
        else:
            remaining = self.max_attempts - self.attempts
            db.session.commit()
            return False, f"Invalid verification code. {remaining} attempt(s) remaining."

    def to_dict(self):
        return {
            'id': self.id,
            'transaction_id': self.transaction_id,
            'code_type': self.code_type,
            'attempts': self.attempts,
            'max_attempts': self.max_attempts,
            'is_used': self.is_used,
            'is_expired': datetime.utcnow() > self.expires_at,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'used_at': self.used_at.isoformat() if self.used_at else None
        }
