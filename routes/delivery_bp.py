from flask import Blueprint, request, jsonify
from extensions import db
from models.transaction import Transaction
from models.delivery import DeliveryAssignment
from services.auth_service import jwt_required, role_required
from services.verification_service import verify_pickup, verify_handover

delivery_bp = Blueprint('delivery_bp', __name__)

@delivery_bp.route('/assigned', methods=['GET'])
@jwt_required
def list_assigned_deliveries():
    user = request.current_user
    
    # Courier can see deliveries specifically assigned to them OR available orders ready for pickup
    query = Transaction.query.filter(
        Transaction.delivery_type.in_(['courier', 'collection_point']),
        Transaction.status.in_(['payment_held', 'order_prepared', 'in_transit', 'delivered', 'in_inspection', 'completed'])
    )
    
    if user.role == 'courier':
        query = query.filter(
            (Transaction.courier_id == user.id) | 
            (Transaction.courier_id == None) & (Transaction.status.in_(['order_prepared', 'payment_held']))
        )
        
    deliveries = query.order_by(Transaction.updated_at.desc()).all()
    
    results = []
    for tx in deliveries:
        item = tx.to_dict()
        item['delivery_assignment'] = tx.delivery_assignment.to_dict() if tx.delivery_assignment else None
        results.append(item)
        
    return jsonify({'deliveries': results, 'total': len(results)}), 200

@delivery_bp.route('/verify-pickup', methods=['POST'])
@jwt_required
def courier_verify_pickup():
    user = request.current_user
    data = request.get_json() or {}
    
    transaction_ref = data.get('transaction_ref')
    code = data.get('code', '').strip()
    
    if not transaction_ref or not code:
        return jsonify({'error': 'Transaction reference and 6-digit pickup code are required.'}), 400
        
    tx = Transaction.query.filter_by(reference=transaction_ref).first()
    if not tx:
        return jsonify({'error': 'Transaction not found.'}), 404
        
    success, msg = verify_pickup(tx.id, user.id, code)
    if not success:
        return jsonify({'error': msg}), 400
        
    return jsonify({
        'message': msg,
        'transaction_status': tx.status,
        'delivery_status': tx.delivery_assignment.current_status if tx.delivery_assignment else 'picked_up'
    }), 200

@delivery_bp.route('/verify-handover', methods=['POST'])
@jwt_required
def courier_verify_handover():
    user = request.current_user
    data = request.get_json() or {}
    
    transaction_ref = data.get('transaction_ref')
    code = data.get('code', '').strip()
    
    if not transaction_ref or not code:
        return jsonify({'error': 'Transaction reference and 6-digit handover code are required.'}), 400
        
    tx = Transaction.query.filter_by(reference=transaction_ref).first()
    if not tx:
        return jsonify({'error': 'Transaction not found.'}), 404
        
    success, msg = verify_handover(tx.id, user.id, code)
    if not success:
        return jsonify({'error': msg}), 400
        
    return jsonify({
        'message': msg,
        'transaction_status': tx.status,
        'delivery_status': tx.delivery_assignment.current_status if tx.delivery_assignment else 'delivered'
    }), 200
