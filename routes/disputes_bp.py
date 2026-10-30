from flask import Blueprint, request, jsonify
from extensions import db
from models.dispute import Dispute
from models.transaction import Transaction
from services.auth_service import jwt_required

disputes_bp = Blueprint('disputes_bp', __name__)

@disputes_bp.route('', methods=['GET'])
@jwt_required
def list_disputes():
    user = request.current_user
    
    if user.role == 'admin':
        disputes = Dispute.query.order_by(Dispute.created_at.desc()).all()
    else:
        # User is initiator or buyer or seller on the disputed transaction
        disputes = Dispute.query.join(Transaction).filter(
            (Dispute.initiator_id == user.id) |
            (Transaction.buyer_id == user.id) |
            (Transaction.seller_id == user.id)
        ).order_by(Dispute.created_at.desc()).all()
        
    results = []
    for d in disputes:
        item = d.to_dict()
        item['transaction'] = d.transaction.to_dict() if d.transaction else None
        results.append(item)
        
    return jsonify({'disputes': results, 'total': len(results)}), 200

@disputes_bp.route('/<int:dispute_id>', methods=['GET'])
@jwt_required
def get_dispute(dispute_id):
    user = request.current_user
    dispute = Dispute.query.get(dispute_id)
    if not dispute:
        return jsonify({'error': 'Dispute not found.'}), 404
        
    tx = dispute.transaction
    if user.role != 'admin' and user.id not in [dispute.initiator_id, tx.buyer_id, tx.seller_id]:
        return jsonify({'error': 'Unauthorized to view this dispute.'}), 403
        
    item = dispute.to_dict()
    item['transaction'] = tx.to_dict()
    return jsonify({'dispute': item}), 200
