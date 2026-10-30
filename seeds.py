import json
from datetime import datetime, timedelta
from extensions import db
from models.user import User
from models.transaction import Transaction
from models.terms import TransactionTerms
from models.payment import Payment
from models.delivery import DeliveryAssignment
from models.verification import VerificationCode
from models.events import DeliveryEvent
from models.dispute import Dispute
from models.ledger import LedgerEntry
from models.notification import Notification
from services.verification_service import generate_pickup_code, generate_handover_code

def seed_database():
    """Seeds demo accounts and realistic Kenyan marketplace transactions."""
    
    # 1. Create Demo Users
    users_data = [
        {
            'email': 'buyer@bridgeescrow.co.ke',
            'full_name': 'Wanjiku Kamau',
            'phone_number': '+254712345678',
            'role': 'buyer',
            'kyc_status': 'verified',
            'password': 'Password123!'
        },
        {
            'email': 'seller@bridgeescrow.co.ke',
            'full_name': 'Juma Omondi',
            'phone_number': '+254722987654',
            'role': 'seller',
            'kyc_status': 'verified',
            'password': 'Password123!'
        },
        {
            'email': 'courier@bridgeescrow.co.ke',
            'full_name': 'BodaExpress Couriers (Kiprono)',
            'phone_number': '+254733112233',
            'role': 'courier',
            'kyc_status': 'verified',
            'password': 'Password123!'
        },
        {
            'email': 'admin@bridgeescrow.co.ke',
            'full_name': 'System Administrator',
            'phone_number': '+254700000001',
            'role': 'admin',
            'kyc_status': 'verified',
            'password': 'AdminSecret123!'
        }
    ]
    
    user_map = {}
    for udata in users_data:
        existing = User.query.filter_by(email=udata['email']).first()
        if not existing:
            u = User(
                email=udata['email'],
                full_name=udata['full_name'],
                phone_number=udata['phone_number'],
                role=udata['role'],
                kyc_status=udata['kyc_status']
            )
            u.set_password(udata['password'])
            db.session.add(u)
            db.session.flush()
            user_map[udata['role']] = u
        else:
            user_map[udata['role']] = existing
            
    db.session.commit()
    buyer = user_map['buyer']
    seller = user_map['seller']
    courier = user_map['courier']
    admin = user_map['admin']
    
    # Check if sample transactions already exist
    if Transaction.query.count() > 0:
        return
        
    # Transaction 1: In Transit (iPhone 15 Pro Max) - Perfect for testing Handover verification!
    tx1 = Transaction(
        reference='BE-2610-IPHONE',
        title='Apple iPhone 15 Pro Max 256GB (Natural Titanium)',
        description='Brand new sealed box with 1-year Apple care warranty. Delivered via verified courier.',
        category='goods_electronics',
        buyer_id=buyer.id,
        seller_id=seller.id,
        courier_id=courier.id,
        amount=185000.0,
        platform_fee=4625.0,  # 2.5%
        delivery_fee=750.0,
        total_amount=190375.0,
        delivery_type='courier',
        status='in_transit',
        inspection_period_days=3,
        created_at=datetime.utcnow() - timedelta(days=1)
    )
    db.session.add(tx1)
    db.session.flush()
    
    t1_terms = TransactionTerms(
        transaction_id=tx1.id,
        delivery_method='courier',
        inspection_period_days=3,
        acceptance_conditions='Verification of unopened box serial number matching receipt and hardware diagnostic run.',
        refund_conditions='100% refund if box seal is broken or serial mismatch.',
        release_requirements='Buyer digital inspection approval or 72-hour window elapsed.',
        buyer_accepted=True,
        seller_accepted=True,
        buyer_accepted_at=datetime.utcnow() - timedelta(days=1, hours=2),
        seller_accepted_at=datetime.utcnow() - timedelta(days=1, hours=1)
    )
    db.session.add(t1_terms)
    
    p1 = Payment(
        transaction_id=tx1.id,
        user_id=buyer.id,
        amount=tx1.total_amount,
        currency='KES',
        provider='mpesa',
        checkout_request_id='ws_CO_26102026_IPHONE',
        mpesa_receipt_number='QHL789KMN1',
        phone_number=buyer.phone_number,
        status='completed',
        completed_at=datetime.utcnow() - timedelta(hours=20)
    )
    db.session.add(p1)
    
    d1 = DeliveryAssignment(
        transaction_id=tx1.id,
        courier_id=courier.id,
        pickup_address='Sarit Centre Mall, Westlands, Shop 42',
        dropoff_address='Riverside Drive, Apartment 4B, Nairobi',
        recipient_name=buyer.full_name,
        recipient_phone=buyer.phone_number,
        current_status='in_transit',
        pickup_time=datetime.utcnow() - timedelta(hours=3),
        notes='Fragile electronics packaging. Handle with care.'
    )
    db.session.add(d1)
    
    # Create used pickup code
    code_pick, _ = VerificationCode.generate_code(tx1.id, 'pickup')
    code_pick.is_used = True
    code_pick.used_at = datetime.utcnow() - timedelta(hours=3)
    code_pick.used_by_user_id = courier.id
    
    # Create active handover code for buyer!
    code_hand, raw_handover_code = VerificationCode.generate_code(tx1.id, 'handover')
    
    DeliveryEvent.log(tx1.id, 'deal_created', 'Deal initiated by buyer.', buyer.id)
    DeliveryEvent.log(tx1.id, 'terms_accepted', 'Agreed terms signed by both parties.', seller.id)
    DeliveryEvent.log(tx1.id, 'payment_verified', f'M-Pesa deposit KES 190,375.00 verified ({p1.mpesa_receipt_number}). Funds secured in Escrow.', buyer.id)
    DeliveryEvent.log(tx1.id, 'order_prepared', 'Seller packaged item and marked ready for pickup.', seller.id)
    DeliveryEvent.log(tx1.id, 'pickup_verified', 'Courier verified seller pickup PIN. Package en route to buyer.', courier.id)
    
    # Ledger hold for buyer
    l1 = LedgerEntry(
        user_id=buyer.id,
        transaction_id=tx1.id,
        entry_type='escrow_deposit',
        amount=tx1.total_amount,
        direction='credit',
        balance_after=tx1.total_amount,
        description=f"Escrow Vault Deposit for {tx1.reference}",
        reference='LED-TX1-DEP',
        provider='Safaricom M-Pesa'
    )
    db.session.add(l1)
    
    # Transaction 2: Payment Held (UI/UX Design Contract)
    tx2 = Transaction(
        reference='BE-2610-FINTECH-UI',
        title='Fintech Mobile App UI/UX Design Sprint (Figma)',
        description='Complete high-fidelity design system and 28 clickable prototype screens for SACCO mobile banking app.',
        category='freelance_services',
        buyer_id=buyer.id,
        seller_id=seller.id,
        amount=75000.0,
        platform_fee=1875.0,
        delivery_fee=0.0,
        total_amount=76875.0,
        delivery_type='digital_service',
        status='payment_held',
        inspection_period_days=5,
        created_at=datetime.utcnow() - timedelta(days=2)
    )
    db.session.add(tx2)
    db.session.flush()
    
    t2_terms = TransactionTerms(
        transaction_id=tx2.id,
        delivery_method='digital_service',
        inspection_period_days=5,
        acceptance_conditions='Delivery of unlocked Figma file with full design token documentation.',
        refund_conditions='50% milestone refund if initial concept is rejected within 48 hours.',
        release_requirements='Buyer design approval in writing.',
        buyer_accepted=True,
        seller_accepted=True
    )
    db.session.add(t2_terms)
    
    p2 = Payment(
        transaction_id=tx2.id,
        user_id=buyer.id,
        amount=tx2.total_amount,
        currency='KES',
        provider='mpesa',
        checkout_request_id='ws_CO_26102026_FIGMA',
        mpesa_receipt_number='QHL994KL02',
        phone_number=buyer.phone_number,
        status='completed',
        completed_at=datetime.utcnow() - timedelta(days=1)
    )
    db.session.add(p2)
    DeliveryEvent.log(tx2.id, 'deal_created', 'Digital contract initialized.', buyer.id)
    DeliveryEvent.log(tx2.id, 'terms_accepted', 'Milestone conditions ratified.', seller.id)
    DeliveryEvent.log(tx2.id, 'payment_verified', f'M-Pesa payment KES 76,875.00 confirmed ({p2.mpesa_receipt_number}). Vault holding active.', buyer.id)
    
    # Transaction 3: In Inspection (Toyota Land Cruiser Spare Parts)
    tx3 = Transaction(
        reference='BE-2610-PARTS',
        title='OEM Toyota Land Cruiser Prado Shock Absorbers (Pair)',
        description='Genuine Japanese Tokico gas suspension dampers with seal certification.',
        category='vehicles',
        buyer_id=buyer.id,
        seller_id=seller.id,
        courier_id=courier.id,
        amount=48000.0,
        platform_fee=1200.0,
        delivery_fee=1000.0,
        total_amount=50200.0,
        delivery_type='courier',
        status='in_inspection',
        inspection_period_days=3,
        inspection_deadline=datetime.utcnow() + timedelta(days=2, hours=14),
        created_at=datetime.utcnow() - timedelta(days=3)
    )
    db.session.add(tx3)
    db.session.flush()
    
    t3_terms = TransactionTerms(
        transaction_id=tx3.id,
        delivery_method='courier',
        inspection_period_days=3,
        acceptance_conditions='Mechanic inspection confirms OEM stamps and pressure testing.',
        refund_conditions='Return delivery paid by seller if non-genuine.',
        release_requirements='Buyer acceptance upon mechanic fitment check.',
        buyer_accepted=True,
        seller_accepted=True
    )
    db.session.add(t3_terms)
    
    d3 = DeliveryAssignment(
        transaction_id=tx3.id,
        courier_id=courier.id,
        pickup_address='Industrial Area, Enterprise Road, Godown 12',
        dropoff_address='Karen Auto Garage, Dagoretti Road',
        recipient_name=buyer.full_name,
        recipient_phone=buyer.phone_number,
        current_status='delivered',
        pickup_time=datetime.utcnow() - timedelta(days=1, hours=8),
        delivery_time=datetime.utcnow() - timedelta(hours=10)
    )
    db.session.add(d3)
    DeliveryEvent.log(tx3.id, 'deal_created', 'Deal initiated.', buyer.id)
    DeliveryEvent.log(tx3.id, 'payment_verified', 'Funds of KES 50,200.00 secured in escrow.', buyer.id)
    DeliveryEvent.log(tx3.id, 'pickup_verified', 'Courier collected from Industrial Area.', courier.id)
    DeliveryEvent.log(tx3.id, 'handover_verified', 'Delivered to Karen garage. 3-day inspection timer running.', courier.id)
    
    # Transaction 4: Completed (Sony WH-1000XM5 Headphones)
    tx4 = Transaction(
        reference='BE-2610-SONY-ANC',
        title='Sony WH-1000XM5 Noise Canceling Headphones',
        description='Midnight blue wireless ANC headphones, mint condition with carrying case.',
        category='goods_electronics',
        buyer_id=buyer.id,
        seller_id=seller.id,
        courier_id=courier.id,
        amount=34000.0,
        platform_fee=850.0,
        delivery_fee=500.0,
        total_amount=35350.0,
        delivery_type='courier',
        status='completed',
        inspection_period_days=2,
        completed_at=datetime.utcnow() - timedelta(days=4),
        created_at=datetime.utcnow() - timedelta(days=7)
    )
    db.session.add(tx4)
    db.session.flush()
    
    # Add ledger entries for completed sale
    db.session.add(LedgerEntry(
        user_id=seller.id,
        transaction_id=tx4.id,
        entry_type='seller_settlement',
        amount=tx4.amount,
        direction='credit',
        balance_after=tx4.amount,
        description=f"Net sale settlement from {tx4.reference}",
        reference='LED-COMP-01',
        provider='M-Pesa / Escrow Vault'
    ))
    
    # Transaction 5: Disputed (MacBook Pro M3 Max)
    tx5 = Transaction(
        reference='BE-2610-MACBOOK',
        title='Apple MacBook Pro 16" M3 Max 36GB RAM',
        description='Refurbished Grade A unit with 1TB SSD and power adapter.',
        category='goods_electronics',
        buyer_id=buyer.id,
        seller_id=seller.id,
        amount=310000.0,
        platform_fee=7750.0,
        delivery_fee=1200.0,
        total_amount=318950.0,
        delivery_type='courier',
        status='disputed',
        inspection_period_days=3,
        created_at=datetime.utcnow() - timedelta(days=5)
    )
    db.session.add(tx5)
    db.session.flush()
    
    dispute5 = Dispute(
        transaction_id=tx5.id,
        initiator_id=buyer.id,
        reason='not_as_described',
        description='Listing stated Grade A condition with battery health at 98%. Diagnostics show battery health is 79% with service recommended error and dent on lower casing.',
        evidence_urls=json.dumps([
            'https://bridgeescrow.co.ke/cdn/evidence/macbook-battery-report.pdf',
            'https://bridgeescrow.co.ke/cdn/evidence/chassis-damage-photo.jpg'
        ]),
        status='open'
    )
    db.session.add(dispute5)
    DeliveryEvent.log(tx5.id, 'deal_created', 'Deal initiated.', buyer.id)
    DeliveryEvent.log(tx5.id, 'payment_verified', 'Escrow funds KES 318,950.00 secured.', buyer.id)
    DeliveryEvent.log(tx5.id, 'dispute_opened', 'Buyer raised dispute for hardware condition discrepancy. Funds frozen.', buyer.id)
    
    # Add welcome notifications
    db.session.add(Notification(
        user_id=buyer.id,
        title='Welcome to BridgeEscrow Kenya',
        message='Your secure escrow marketplace account is ready. Trade with complete buyer protection.',
        link='/transactions'
    ))
    db.session.add(Notification(
        user_id=seller.id,
        title='Seller Account Verified',
        message='You are eligible to create protected deals with guaranteed settlement upon buyer acceptance.',
        link='/transactions'
    ))
    
    db.session.commit()
    print("Database successfully seeded with realistic Kenyan Escrow deals and demo accounts!")
