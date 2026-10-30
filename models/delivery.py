from datetime import datetime
from extensions import db

class DeliveryAssignment(db.Model):
    __tablename__ = 'delivery_assignments'

    id = db.Column(db.Integer, primary_key=True)
    transaction_id = db.Column(db.Integer, db.ForeignKey('transactions.id'), nullable=False, unique=True)
    courier_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    pickup_address = db.Column(db.String(255), nullable=False)
    dropoff_address = db.Column(db.String(255), nullable=False)
    recipient_name = db.Column(db.String(120), nullable=False)
    recipient_phone = db.Column(db.String(20), nullable=False)
    
    current_status = db.Column(db.String(30), nullable=False, default='assigned')  # assigned, ready_for_pickup, picked_up, in_transit, delivered, failed
    pickup_time = db.Column(db.DateTime, nullable=True)
    delivery_time = db.Column(db.DateTime, nullable=True)
    notes = db.Column(db.Text, nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'transaction_id': self.transaction_id,
            'courier_id': self.courier_id,
            'pickup_address': self.pickup_address,
            'dropoff_address': self.dropoff_address,
            'recipient_name': self.recipient_name,
            'recipient_phone': self.recipient_phone,
            'current_status': self.current_status,
            'pickup_time': self.pickup_time.isoformat() if self.pickup_time else None,
            'delivery_time': self.delivery_time.isoformat() if self.delivery_time else None,
            'notes': self.notes
        }
