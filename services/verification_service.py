from datetime import datetime, timedelta
from extensions import db
from models.transaction import Transaction
from models.verification import VerificationCode
from models.events import DeliveryEvent
from services.notification_service import send_notification

def generate_pickup_code(transaction_id, requesting_user_id):
    """
    Authorized seller requests the pickup verification code to show the courier.
    Returns (raw_6_digit_code, VerificationCode_instance)
    """
    tx = Transaction.query.get(transaction_id)
    if not tx:
        return None, "Transaction not found"
        
    if tx.seller_id != requesting_user_id:
        return None, "Only the authorized seller can view the pickup verification code."
        
    if tx.status not in ['payment_held', 'order_prepared']:
        return None, f"Pickup code is only available once payment is secured in escrow. Current status: {tx.status}"
        
    code_obj, raw_code = VerificationCode.generate_code(transaction_id, 'pickup', expiry_hours=48)
    db.session.commit()
    
    DeliveryEvent.log(
        transaction_id=tx.id,
        event_type='pickup_code_generated',
        description=f"Seller {tx.seller.full_name} generated dispatch pickup code.",
        actor_id=requesting_user_id
    )
    db.session.commit()
    
    return raw_code, "Pickup code generated successfully."

def generate_handover_code(transaction_id, requesting_user_id):
    """
    Authorized buyer requests the handover verification code to give to the courier upon receiving goods.
    Returns (raw_6_digit_code, VerificationCode_instance)
    """
    tx = Transaction.query.get(transaction_id)
    if not tx:
        return None, "Transaction not found"
        
    if tx.buyer_id != requesting_user_id:
        return None, "Only the authorized buyer can view the handover verification code."
        
    if tx.status not in ['order_prepared', 'in_transit']:
        return None, f"Handover code is available during transit/delivery. Current status: {tx.status}"
        
    code_obj, raw_code = VerificationCode.generate_code(transaction_id, 'handover', expiry_hours=48)
    db.session.commit()
    
    DeliveryEvent.log(
        transaction_id=tx.id,
        event_type='handover_code_generated',
        description=f"Buyer {tx.buyer.full_name} retrieved handover verification code.",
        actor_id=requesting_user_id
    )
    db.session.commit()
    
    return raw_code, "Handover code generated successfully."

def verify_pickup(transaction_id, courier_id, input_code):
    """
    Courier enters the 6-digit pickup code received from the seller.
    Backend verifies hash, transaction association, expiry, attempts limit, and non-used status.
    """
    tx = Transaction.query.get(transaction_id)
    if not tx:
        return False, "Transaction not found"
        
    if tx.courier_id and tx.courier_id != courier_id:
        return False, "This delivery is assigned to a different authorized courier."
        
    if tx.status not in ['payment_held', 'order_prepared']:
        return False, f"Transaction is not ready for pickup. Current status: {tx.status}"
        
    # Look up pickup verification code
    code_record = VerificationCode.query.filter_by(
        transaction_id=transaction_id,
        code_type='pickup',
        is_used=False
    ).order_by(VerificationCode.created_at.desc()).first()
    
    if not code_record:
        return False, "No active pickup code found for this transaction. Seller must generate a pickup code."
        
    is_valid, msg = code_record.verify(input_code, courier_id)
    if not is_valid:
        return False, msg
        
    # State transition
    tx.status = 'in_transit'
    if tx.delivery_assignment:
        tx.delivery_assignment.current_status = 'picked_up'
        tx.delivery_assignment.pickup_time = datetime.utcnow()
        if not tx.delivery_assignment.courier_id:
            tx.delivery_assignment.courier_id = courier_id
    tx.courier_id = courier_id
    
    DeliveryEvent.log(
        transaction_id=tx.id,
        event_type='pickup_verified',
        description=f"Courier verified pickup with seller. Package is now in transit.",
        actor_id=courier_id
    )
    
    send_notification(
        tx.buyer_id,
        "Package Picked Up!",
        f"Your order '{tx.title}' has been collected by the courier and is in transit.",
        f"/transactions/{tx.reference}"
    )
    send_notification(
        tx.seller_id,
        "Pickup Confirmed",
        f"Courier confirmed pickup for '{tx.title}'. Order is in transit.",
        f"/transactions/{tx.reference}"
    )
    
    db.session.commit()
    return True, "Pickup successfully verified. Package is now in transit."

def verify_handover(transaction_id, courier_id, input_code):
    """
    Courier enters the 6-digit handover code received from the buyer upon delivery.
    Backend verifies code and transitions to 'delivered' and 'in_inspection'.
    CRITICAL: Courier handover must NOT automatically release funds!
    """
    tx = Transaction.query.get(transaction_id)
    if not tx:
        return False, "Transaction not found"
        
    if tx.courier_id and tx.courier_id != courier_id:
        return False, "This delivery is assigned to a different authorized courier."
        
    if tx.status != 'in_transit':
        return False, f"Handover can only be verified for packages currently in transit. Current status: {tx.status}"
        
    code_record = VerificationCode.query.filter_by(
        transaction_id=transaction_id,
        code_type='handover',
        is_used=False
    ).order_by(VerificationCode.created_at.desc()).first()
    
    if not code_record:
        return False, "No active handover code found. Buyer must provide their handover verification code."
        
    is_valid, msg = code_record.verify(input_code, courier_id)
    if not is_valid:
        return False, msg
        
    # State transition to inspection
    tx.status = 'in_inspection'
    days = tx.inspection_period_days or 3
    tx.inspection_deadline = datetime.utcnow() + timedelta(days=days)
    
    if tx.delivery_assignment:
        tx.delivery_assignment.current_status = 'delivered'
        tx.delivery_assignment.delivery_time = datetime.utcnow()
        
    DeliveryEvent.log(
        transaction_id=tx.id,
        event_type='handover_verified',
        description=f"Courier handover verified by buyer code. {days}-day inspection period has begun. Funds remain secured in escrow.",
        actor_id=courier_id
    )
    
    send_notification(
        tx.buyer_id,
        "Handover Verified — Inspection Period Started",
        f"You have received '{tx.title}'. You have {days} days to inspect and accept or raise a dispute.",
        f"/transactions/{tx.reference}"
    )
    send_notification(
        tx.seller_id,
        "Package Handed Over",
        f"Courier successfully handed over '{tx.title}'. Buyer has entered the inspection window.",
        f"/transactions/{tx.reference}"
    )
    
    db.session.commit()
    return True, f"Handover confirmed! Buyer has now entered the {days}-day inspection period. Escrow funds remain safely secured."
