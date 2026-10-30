from datetime import datetime
from extensions import db

class Transaction(db.Model):
    __tablename__ = 'transactions'

    id = db.Column(db.Integer, primary_key=True)
    reference = db.Column(db.String(32), unique=True, nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(50), nullable=False)  # goods_electronics, parcels, vehicles, freelance_services, digital_products, wholesale_orders, milestone_work
    
    buyer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    seller_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    courier_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    amount = db.Column(db.Float, nullable=False)  # KES
    platform_fee = db.Column(db.Float, nullable=False, default=0.0)
    delivery_fee = db.Column(db.Float, nullable=False, default=0.0)
    total_amount = db.Column(db.Float, nullable=False)  # amount + platform_fee + delivery_fee
    
    delivery_type = db.Column(db.String(30), nullable=False, default='courier')  # courier, in_person, collection_point, digital_service
    status = db.Column(db.String(30), nullable=False, default='draft')
    # Valid statuses:
    # draft: newly created, awaiting agreement
    # pending_payment: terms agreed, waiting for buyer M-Pesa deposit
    # payment_held: funds verified in Escrow Vault
    # order_prepared: seller marked ready for dispatch
    # in_transit: courier verified pickup code, in delivery
    # delivered: courier verified handover code, delivered
    # in_inspection: buyer inspecting goods
    # completed: buyer accepted goods, funds released to seller
    # disputed: active dispute, funds strictly locked
    # refunded: refund resolved to buyer
    # cancelled: cancelled before payment
    
    inspection_period_days = db.Column(db.Integer, nullable=False, default=3)
    inspection_deadline = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    terms = db.relationship('TransactionTerms', backref='transaction', uselist=False, cascade='all, delete-orphan')
    payments = db.relationship('Payment', backref='transaction', lazy=True, cascade='all, delete-orphan')
    delivery_assignment = db.relationship('DeliveryAssignment', backref='transaction', uselist=False, cascade='all, delete-orphan')
    verification_codes = db.relationship('VerificationCode', backref='transaction', lazy=True, cascade='all, delete-orphan')
    events = db.relationship('DeliveryEvent', backref='transaction', lazy=True, order_by='DeliveryEvent.created_at.asc()', cascade='all, delete-orphan')
    disputes = db.relationship('Dispute', backref='transaction', lazy=True, order_by='Dispute.created_at.desc()', cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'reference': self.reference,
            'title': self.title,
            'description': self.description,
            'category': self.category,
            'buyer_id': self.buyer_id,
            'seller_id': self.seller_id,
            'courier_id': self.courier_id,
            'buyer': self.buyer.to_dict() if self.buyer else None,
            'seller': self.seller.to_dict() if self.seller else None,
            'courier': self.courier.to_dict() if self.courier else None,
            'amount': self.amount,
            'platform_fee': self.platform_fee,
            'delivery_fee': self.delivery_fee,
            'total_amount': self.total_amount,
            'delivery_type': self.delivery_type,
            'status': self.status,
            'inspection_period_days': self.inspection_period_days,
            'inspection_deadline': self.inspection_deadline.isoformat() if self.inspection_deadline else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'terms': self.terms.to_dict() if self.terms else None,
            'has_active_dispute': any(d.status in ['open', 'under_review'] for d in self.disputes),
            'dispute_count': len(self.disputes)
        }
