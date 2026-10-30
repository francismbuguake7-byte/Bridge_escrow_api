import uuid
from datetime import datetime, timedelta
from extensions import db
from models.transaction import Transaction
from models.terms import TransactionTerms
from models.delivery import DeliveryAssignment
from models.events import DeliveryEvent
from models.dispute import Dispute
from models.audit import AuditLog
from services.ledger_service import record_ledger_entry
from services.notification_service import send_notification

def calculate_escrow_fees(amount, delivery_fee=0.0, fee_percentage=0.025, min_fee=50.0):
    platform_fee = max(min_fee, round(amount * fee_percentage, 2))
    total_amount = round(amount + platform_fee + delivery_fee, 2)
    return platform_fee, total_amount

def create_escrow_deal(buyer_id, seller_id, title, description, category, amount, delivery_fee, delivery_type,
                       inspection_period_days, acceptance_conditions, refund_conditions, release_requirements,
                       pickup_address="", dropoff_address="", recipient_name="", recipient_phone=""):
    platform_fee, total = calculate_escrow_fees(amount, delivery_fee)
    ref = f"BE-{datetime.utcnow().strftime('%y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
    
    tx = Transaction(
        reference=ref,
        title=title,
        description=description,
        category=category,
        buyer_id=buyer_id,
        seller_id=seller_id,
        amount=amount,
        platform_fee=platform_fee,
        delivery_fee=delivery_fee,
        total_amount=total,
        delivery_type=delivery_type,
        status='draft',
        inspection_period_days=inspection_period_days
    )
    db.session.add(tx)
    db.session.flush()
    
    terms = TransactionTerms(
        transaction_id=tx.id,
        delivery_method=delivery_type,
        inspection_period_days=inspection_period_days,
        acceptance_conditions=acceptance_conditions or "Inspection confirms goods match listed description, condition, and full specifications.",
        refund_conditions=refund_conditions or "Full refund if items are non-delivered, damaged in transit, or substantively misrepresented.",
        release_requirements=release_requirements or "Buyer explicit digital acceptance or expiration of uncontested inspection period.",
        buyer_accepted=True,  # Creator is considered to have accepted terms
        buyer_accepted_at=datetime.utcnow()
    )
    db.session.add(terms)
    
    # If physical delivery, create assignment
    if delivery_type in ['courier', 'collection_point', 'in_person']:
        assignment = DeliveryAssignment(
            transaction_id=tx.id,
            pickup_address=pickup_address or "Seller Registered Dispatch Address",
            dropoff_address=dropoff_address or "Buyer Delivery Address",
            recipient_name=recipient_name or "Authorized Recipient",
            recipient_phone=recipient_phone or "+254700000000",
            current_status='assigned'
        )
        db.session.add(assignment)
        
    DeliveryEvent.log(
        transaction_id=tx.id,
        event_type='deal_created',
        description=f"Escrow transaction {ref} initiated for KES {amount:,.2f}.",
        actor_id=buyer_id
    )
    
    send_notification(
        seller_id,
        "New Escrow Deal Created",
        f"A new deal '{title}' has been created with you. Please review and accept the agreed terms.",
        f"/transactions/{ref}"
    )
    
    db.session.commit()
    return tx

def accept_deal_terms(transaction_id, user_id):
    tx = Transaction.query.get(transaction_id)
    if not tx:
        return False, "Transaction not found"
        
    terms = tx.terms
    if not terms:
        return False, "Transaction terms record missing"
        
    if user_id == tx.buyer_id:
        terms.buyer_accepted = True
        terms.buyer_accepted_at = datetime.utcnow()
    elif user_id == tx.seller_id:
        terms.seller_accepted = True
        terms.seller_accepted_at = datetime.utcnow()
    else:
        return False, "Only parties to this transaction may accept terms"
        
    # Check if both have accepted
    if terms.buyer_accepted and terms.seller_accepted:
        tx.status = 'pending_payment'
        DeliveryEvent.log(
            transaction_id=tx.id,
            event_type='terms_accepted',
            description="Both Buyer and Seller accepted the deal terms. Awaiting M-Pesa escrow deposit.",
            actor_id=user_id
        )
        send_notification(
            tx.buyer_id,
            "Terms Accepted — Deposit Ready",
            f"Seller accepted deal terms for '{tx.title}'. Please deposit KES {tx.total_amount:,.2f} into Escrow.",
            f"/transactions/{tx.reference}"
        )
    else:
        DeliveryEvent.log(
            transaction_id=tx.id,
            event_type='terms_partially_accepted',
            description="Deal terms accepted by counterparty.",
            actor_id=user_id
        )
        
    db.session.commit()
    return True, "Terms accepted successfully."

def mark_order_prepared(transaction_id, seller_id):
    tx = Transaction.query.get(transaction_id)
    if not tx:
        return False, "Transaction not found"
        
    if tx.seller_id != seller_id:
        return False, "Only the seller can mark the order as prepared."
        
    if tx.status != 'payment_held':
        return False, f"Order cannot be marked ready in status: {tx.status}. Payment must be secured in escrow first."
        
    tx.status = 'order_prepared'
    if tx.delivery_assignment:
        tx.delivery_assignment.current_status = 'ready_for_pickup'
        
    DeliveryEvent.log(
        transaction_id=tx.id,
        event_type='order_prepared',
        description=f"Seller {tx.seller.full_name} marked order prepared and ready for dispatch.",
        actor_id=seller_id
    )
    
    send_notification(
        tx.buyer_id,
        "Order Prepared!",
        f"Seller has prepared your order '{tx.title}'. Courier dispatch underway.",
        f"/transactions/{tx.reference}"
    )
    
    db.session.commit()
    return True, "Order marked as prepared and ready for courier pickup."

def buyer_accept_and_release(transaction_id, buyer_id):
    """
    Buyer finishes inspection and approves release of funds to the seller.
    Strictly blocked if there is an active dispute!
    """
    tx = Transaction.query.get(transaction_id)
    if not tx:
        return False, "Transaction not found"
        
    if tx.buyer_id != buyer_id:
        return False, "Only the authorized buyer can approve funds release."
        
    # Check for active dispute or disputed state first
    active_dispute = Dispute.query.filter(
        Dispute.transaction_id == tx.id,
        Dispute.status.in_(['open', 'under_review'])
    ).first()
    
    if active_dispute or tx.status == 'disputed':
        return False, "Funds are locked due to an active dispute. The dispute must be resolved by an administrator before release."

    if tx.status not in ['in_inspection', 'delivered', 'payment_held', 'order_prepared']:
        # Note: digital goods might not have delivery steps
        return False, f"Cannot release funds in current transaction state: {tx.status}"
        
    # Release funds
    tx.status = 'completed'
    tx.completed_at = datetime.utcnow()
    
    # 1. Deduct platform fee from escrow
    record_ledger_entry(
        user_id=tx.buyer_id,
        transaction_id=tx.id,
        entry_type='escrow_release',
        amount=tx.total_amount,
        direction='debit',
        description=f"Escrow release for completed transaction {tx.reference}"
    )
    
    # 2. Credit seller with item amount
    record_ledger_entry(
        user_id=tx.seller_id,
        transaction_id=tx.id,
        entry_type='seller_settlement',
        amount=tx.amount,
        direction='credit',
        description=f"Net sale settlement from {tx.reference} (KES {tx.amount:,.2f})"
    )
    
    # 3. If courier was assigned, credit delivery fee to courier if courier exists
    if tx.delivery_fee > 0 and tx.courier_id:
        record_ledger_entry(
            user_id=tx.courier_id,
            transaction_id=tx.id,
            entry_type='delivery_payout',
            amount=tx.delivery_fee,
            direction='credit',
            description=f"Delivery fee settlement for {tx.reference}"
        )
        
    DeliveryEvent.log(
        transaction_id=tx.id,
        event_type='funds_released',
        description=f"Buyer accepted goods after inspection. Funds of KES {tx.amount:,.2f} released to Seller {tx.seller.full_name}.",
        actor_id=buyer_id
    )
    
    send_notification(
        tx.seller_id,
        "Funds Released to Ledger!",
        f"Buyer approved '{tx.title}'. KES {tx.amount:,.2f} has been settled into your account ledger.",
        f"/wallet"
    )
    
    db.session.commit()
    return True, f"Transaction successfully completed! KES {tx.amount:,.2f} has been released to {tx.seller.full_name}."

def raise_dispute(transaction_id, user_id, reason, description, evidence_urls=None):
    tx = Transaction.query.get(transaction_id)
    if not tx:
        return False, "Transaction not found"
        
    if user_id not in [tx.buyer_id, tx.seller_id]:
        return False, "Only parties to this transaction may open a dispute."
        
    if tx.status in ['draft', 'cancelled', 'refunded', 'completed']:
        return False, f"Cannot open dispute on transaction with status '{tx.status}'."
        
    # Check if existing open dispute
    existing = Dispute.query.filter(
        Dispute.transaction_id == tx.id,
        Dispute.status.in_(['open', 'under_review'])
    ).first()
    if existing:
        return False, "An active dispute is already open for this transaction."
        
    import json
    dispute = Dispute(
        transaction_id=tx.id,
        initiator_id=user_id,
        reason=reason,
        description=description,
        evidence_urls=json.dumps(evidence_urls or []),
        status='open'
    )
    db.session.add(dispute)
    
    # Lock transaction status
    tx.status = 'disputed'
    
    from models.user import User
    initiator_user = User.query.get(user_id)
    initiator_name = initiator_user.full_name if initiator_user else 'Party'
    
    DeliveryEvent.log(
        transaction_id=tx.id,
        event_type='dispute_opened',
        description=f"Dispute raised by {initiator_name}: {reason}. Escrow funds are locked pending admin resolution.",
        actor_id=user_id
    )
    
    counterparty_id = tx.seller_id if user_id == tx.buyer_id else tx.buyer_id
    send_notification(
        counterparty_id,
        "Dispute Opened on Transaction",
        f"A dispute has been opened on '{tx.title}'. Funds are frozen pending resolution.",
        f"/disputes"
    )
    
    db.session.commit()
    return True, "Dispute raised successfully. Escrow funds are locked pending administrator investigation."

def resolve_dispute_by_admin(dispute_id, admin_id, resolution, resolution_notes):
    """
    Admin resolves dispute:
    - 'resolved_buyer_refund': 100% refund to buyer
    - 'resolved_seller_payout': 100% payout to seller
    - 'resolved_split': 50/50 split settlement
    """
    dispute = Dispute.query.get(dispute_id)
    if not dispute:
        return False, "Dispute record not found"
        
    if dispute.status not in ['open', 'under_review']:
        return False, f"Dispute is already resolved ({dispute.status})"
        
    tx = dispute.transaction
    dispute.status = resolution
    dispute.resolution = resolution
    dispute.resolution_notes = resolution_notes
    dispute.resolved_by_admin_id = admin_id
    dispute.resolved_at = datetime.utcnow()
    
    if resolution == 'resolved_buyer_refund':
        tx.status = 'refunded'
        record_ledger_entry(
            user_id=tx.buyer_id,
            transaction_id=tx.id,
            entry_type='buyer_refund',
            amount=tx.amount,
            direction='credit',
            description=f"Dispute resolution: Full refund for {tx.reference}"
        )
        msg = f"Dispute resolved by Admin. Full refund of KES {tx.amount:,.2f} returned to buyer."
    elif resolution == 'resolved_seller_payout':
        tx.status = 'completed'
        tx.completed_at = datetime.utcnow()
        record_ledger_entry(
            user_id=tx.seller_id,
            transaction_id=tx.id,
            entry_type='seller_settlement',
            amount=tx.amount,
            direction='credit',
            description=f"Dispute resolution: Seller payout for {tx.reference}"
        )
        msg = f"Dispute resolved by Admin. Payout of KES {tx.amount:,.2f} awarded to seller."
    elif resolution == 'resolved_split':
        tx.status = 'completed'
        tx.completed_at = datetime.utcnow()
        half_amount = round(tx.amount / 2, 2)
        record_ledger_entry(
            user_id=tx.buyer_id,
            transaction_id=tx.id,
            entry_type='buyer_refund',
            amount=half_amount,
            direction='credit',
            description=f"Dispute resolution: 50% split refund for {tx.reference}"
        )
        record_ledger_entry(
            user_id=tx.seller_id,
            transaction_id=tx.id,
            entry_type='seller_settlement',
            amount=half_amount,
            direction='credit',
            description=f"Dispute resolution: 50% split settlement for {tx.reference}"
        )
        msg = f"Dispute resolved by Admin. Split settlement of KES {half_amount:,.2f} each."
    else:
        dispute.status = 'rejected'
        tx.status = 'in_inspection'
        msg = "Dispute claim rejected. Resumed inspection."
        
    DeliveryEvent.log(
        transaction_id=tx.id,
        event_type='dispute_resolved',
        description=f"Admin resolved dispute: {msg}. Notes: {resolution_notes}",
        actor_id=admin_id
    )
    
    AuditLog.record(
        action='resolve_dispute',
        target_type='Dispute',
        target_id=dispute.id,
        actor_id=admin_id,
        details={'resolution': resolution, 'notes': resolution_notes, 'transaction_ref': tx.reference}
    )
    
    send_notification(tx.buyer_id, "Dispute Ruling Issued", msg, f"/transactions/{tx.reference}")
    send_notification(tx.seller_id, "Dispute Ruling Issued", msg, f"/transactions/{tx.reference}")
    
    db.session.commit()
    return True, msg
