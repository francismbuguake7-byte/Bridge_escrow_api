from flask import Blueprint, request, jsonify
from extensions import db
from models.user import User
from models.transaction import Transaction
from models.verification import VerificationCode
from services.auth_service import jwt_required
from services.escrow_service import (
    create_escrow_deal, accept_deal_terms, mark_order_prepared, 
    buyer_accept_and_release, raise_dispute
)
from services.verification_service import generate_pickup_code, generate_handover_code

transactions_bp = Blueprint('transactions_bp', __name__)

@transactions_bp.route('', methods=['GET'])
@jwt_required
def list_transactions():
    user = request.current_user
    role_filter = request.args.get('role', '').lower()
    status_filter = request.args.get('status', '').strip()
    search = request.args.get('search', '').strip()
    
    query = Transaction.query
    
    # If admin and viewing all:
    if user.role == 'admin' and request.args.get('all') == 'true':
        pass
    else:
        # Default: user is buyer, seller, or assigned courier
        if role_filter == 'buyer':
            query = query.filter_by(buyer_id=user.id)
        elif role_filter == 'seller':
            query = query.filter_by(seller_id=user.id)
        elif role_filter == 'courier':
            query = query.filter_by(courier_id=user.id)
        else:
            query = query.filter(
                (Transaction.buyer_id == user.id) | 
                (Transaction.seller_id == user.id) | 
                (Transaction.courier_id == user.id)
            )
            
    if status_filter:
        query = query.filter_by(status=status_filter)
        
    if search:
        query = query.filter(
            (Transaction.title.ilike(f"%{search}%")) |
            (Transaction.reference.ilike(f"%{search}%")) |
            (Transaction.description.ilike(f"%{search}%"))
        )
        
    transactions = query.order_by(Transaction.created_at.desc()).all()
    return jsonify({
        'transactions': [t.to_dict() for t in transactions],
        'total': len(transactions)
    }), 200

@transactions_bp.route('', methods=['POST'])
@jwt_required
def create_transaction():
    user = request.current_user
    data = request.get_json() or {}
    
    # Validation
    title = data.get('title', '').strip()
    description = data.get('description', '').strip()
    category = data.get('category', 'goods_electronics')
    amount = float(data.get('amount', 0))
    delivery_fee = float(data.get('delivery_fee', 0))
    delivery_type = data.get('delivery_type', 'courier')
    seller_identifier = data.get('seller', '').strip()  # can be email or phone or ID
    
    if not title or not description or amount <= 0:
        return jsonify({'error': 'Title, description, and a valid amount in KES are required.'}), 400
        
    # Find counterparty
    seller = None
    if seller_identifier:
        seller = User.query.filter(
            (User.email == seller_identifier.lower()) | 
            (User.phone_number == seller_identifier)
        ).first()
        
    if not seller:
        # If counterparty doesn't exist, search for default demo seller or create invite placeholder
        seller = User.query.filter_by(email='seller@bridgeescrow.co.ke').first()
        if not seller or seller.id == user.id:
            seller = User.query.filter(User.id != user.id).first()
            
    if not seller:
        return jsonify({'error': 'A counterparty seller account must be specified.'}), 400
        
    inspection_days = int(data.get('inspection_period_days', 3))
    
    tx = create_escrow_deal(
        buyer_id=user.id,
        seller_id=seller.id,
        title=title,
        description=description,
        category=category,
        amount=amount,
        delivery_fee=delivery_fee,
        delivery_type=delivery_type,
        inspection_period_days=inspection_days,
        acceptance_conditions=data.get('acceptance_conditions', ''),
        refund_conditions=data.get('refund_conditions', ''),
        release_requirements=data.get('release_requirements', ''),
        pickup_address=data.get('pickup_address', ''),
        dropoff_address=data.get('dropoff_address', ''),
        recipient_name=data.get('recipient_name', user.full_name),
        recipient_phone=data.get('recipient_phone', user.phone_number)
    )
    
    return jsonify({
        'message': 'Escrow transaction deal created successfully.',
        'transaction': tx.to_dict()
    }), 201

@transactions_bp.route('/<ref>', methods=['GET'])
@jwt_required
def get_transaction_detail(ref):
    user = request.current_user
    tx = Transaction.query.filter_by(reference=ref).first()
    if not tx:
        return jsonify({'error': 'Transaction not found'}), 404
        
    # Authorization check
    is_admin = user.role == 'admin'
    is_party = user.id in [tx.buyer_id, tx.seller_id, tx.courier_id]
    if not is_admin and not is_party:
        return jsonify({'error': 'You are not authorized to view this transaction.'}), 403
        
    tx_dict = tx.to_dict()
    tx_dict['events'] = [e.to_dict() for e in tx.events]
    tx_dict['disputes'] = [d.to_dict() for d in tx.disputes]
    if tx.delivery_assignment:
        tx_dict['delivery_assignment'] = tx.delivery_assignment.to_dict()
        
    # Compute authorized actions for current user
    actions = {
        'can_accept_terms': tx.status == 'draft' and (
            (user.id == tx.buyer_id and not tx.terms.buyer_accepted) or
            (user.id == tx.seller_id and not tx.terms.seller_accepted)
        ),
        'can_pay': tx.status == 'pending_payment' and user.id == tx.buyer_id,
        'can_mark_ready': tx.status == 'payment_held' and user.id == tx.seller_id,
        'can_view_pickup_code': tx.status in ['payment_held', 'order_prepared'] and user.id == tx.seller_id,
        'can_view_handover_code': tx.status in ['order_prepared', 'in_transit'] and user.id == tx.buyer_id,
        'can_accept_and_release': tx.status in ['in_inspection', 'delivered', 'payment_held'] and user.id == tx.buyer_id and not any(d.status in ['open', 'under_review'] for d in tx.disputes),
        'can_raise_dispute': tx.status in ['payment_held', 'order_prepared', 'in_transit', 'delivered', 'in_inspection'] and user.id in [tx.buyer_id, tx.seller_id] and not any(d.status in ['open', 'under_review'] for d in tx.disputes),
        'is_buyer': user.id == tx.buyer_id,
        'is_seller': user.id == tx.seller_id,
        'is_courier': user.id == tx.courier_id,
        'is_admin': is_admin
    }
    tx_dict['permissions'] = actions
    return jsonify({'transaction': tx_dict}), 200

@transactions_bp.route('/<ref>/accept-terms', methods=['POST'])
@jwt_required
def accept_terms(ref):
    user = request.current_user
    tx = Transaction.query.filter_by(reference=ref).first()
    if not tx:
        return jsonify({'error': 'Transaction not found'}), 404
        
    success, msg = accept_deal_terms(tx.id, user.id)
    if not success:
        return jsonify({'error': msg}), 400
        
    return jsonify({'message': msg, 'transaction': tx.to_dict()}), 200

@transactions_bp.route('/<ref>/mark-ready', methods=['POST'])
@jwt_required
def mark_ready(ref):
    user = request.current_user
    tx = Transaction.query.filter_by(reference=ref).first()
    if not tx:
        return jsonify({'error': 'Transaction not found'}), 404
        
    success, msg = mark_order_prepared(tx.id, user.id)
    if not success:
        return jsonify({'error': msg}), 400
        
    return jsonify({'message': msg, 'transaction': tx.to_dict()}), 200

@transactions_bp.route('/<ref>/pickup-code', methods=['GET'])
@jwt_required
def get_pickup_code(ref):
    """
    Authorized seller retrieves the 6-digit pickup verification code to show the courier.
    """
    user = request.current_user
    tx = Transaction.query.filter_by(reference=ref).first()
    if not tx:
        return jsonify({'error': 'Transaction not found'}), 404
        
    raw_code, msg = generate_pickup_code(tx.id, user.id)
    if not raw_code:
        return jsonify({'error': msg}), 400
        
    return jsonify({
        'code': raw_code,
        'code_type': 'pickup',
        'message': 'Provide this 6-digit code to the authorized courier at pickup.'
    }), 200

@transactions_bp.route('/<ref>/handover-code', methods=['GET'])
@jwt_required
def get_handover_code(ref):
    """
    Authorized buyer retrieves the 6-digit handover verification code to give to the courier.
    """
    user = request.current_user
    tx = Transaction.query.filter_by(reference=ref).first()
    if not tx:
        return jsonify({'error': 'Transaction not found'}), 404
        
    raw_code, msg = generate_handover_code(tx.id, user.id)
    if not raw_code:
        return jsonify({'error': msg}), 400
        
    return jsonify({
        'code': raw_code,
        'code_type': 'handover',
        'message': 'Give this 6-digit code to the courier when you physically receive your package.'
    }), 200

@transactions_bp.route('/<ref>/accept-and-release', methods=['POST'])
@jwt_required
def release_funds(ref):
    user = request.current_user
    tx = Transaction.query.filter_by(reference=ref).first()
    if not tx:
        return jsonify({'error': 'Transaction not found'}), 404
        
    success, msg = buyer_accept_and_release(tx.id, user.id)
    if not success:
        return jsonify({'error': msg}), 400
        
    return jsonify({'message': msg, 'transaction': tx.to_dict()}), 200

@transactions_bp.route('/<ref>/dispute', methods=['POST'])
@jwt_required
def open_dispute(ref):
    user = request.current_user
    tx = Transaction.query.filter_by(reference=ref).first()
    if not tx:
        return jsonify({'error': 'Transaction not found'}), 404
        
    data = request.get_json() or {}
    reason = data.get('reason', '').strip()
    description = data.get('description', '').strip()
    evidence_urls = data.get('evidence_urls', [])
    
    if not reason or not description:
        return jsonify({'error': 'Dispute reason and detailed description are required.'}), 400
        
    success, msg = raise_dispute(tx.id, user.id, reason, description, evidence_urls)
    if not success:
        return jsonify({'error': msg}), 400
        
    return jsonify({'message': msg, 'transaction': tx.to_dict()}), 200
