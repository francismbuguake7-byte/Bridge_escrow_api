from flask import Blueprint, request, jsonify
from extensions import db
from models.ledger import LedgerEntry
from models.transaction import Transaction
from services.auth_service import jwt_required
from services.ledger_service import get_user_balance

wallet_bp = Blueprint('wallet_bp', __name__)

@wallet_bp.route('/summary', methods=['GET'])
@jwt_required
def get_wallet_summary():
    user = request.current_user
    settled_balance = get_user_balance(user.id)
    
    # Active Escrow for this user (funds held safely in escrow vault)
    # If user is buyer: payments deposited where status is pending delivery or inspection
    buyer_escrow = db.session.query(db.func.sum(Transaction.total_amount)).filter(
        Transaction.buyer_id == user.id,
        Transaction.status.in_(['payment_held', 'order_prepared', 'in_transit', 'delivered', 'in_inspection', 'disputed'])
    ).scalar() or 0.0
    
    # If user is seller: incoming sales awaiting delivery completion & inspection
    seller_escrow = db.session.query(db.func.sum(Transaction.amount)).filter(
        Transaction.seller_id == user.id,
        Transaction.status.in_(['payment_held', 'order_prepared', 'in_transit', 'delivered', 'in_inspection', 'disputed'])
    ).scalar() or 0.0
    
    # Total historical completed payouts
    completed_sales = db.session.query(db.func.sum(Transaction.amount)).filter(
        Transaction.seller_id == user.id,
        Transaction.status == 'completed'
    ).scalar() or 0.0
    
    return jsonify({
        'settled_balance': max(0.0, settled_balance),
        'buyer_escrow_holding': round(buyer_escrow, 2),
        'seller_pending_settlement': round(seller_escrow, 2),
        'total_completed_sales': round(completed_sales, 2),
        'currency': 'KES',
        'withdrawal_notice': 'Settlements to registered M-Pesa accounts are processed in compliance with Central Bank of Kenya (CBK) settlement windows.'
    }), 200

@wallet_bp.route('/ledger', methods=['GET'])
@jwt_required
def list_ledger_entries():
    user = request.current_user
    entries = LedgerEntry.query.filter_by(user_id=user.id).order_by(LedgerEntry.created_at.desc()).all()
    return jsonify({
        'entries': [e.to_dict() for e in entries],
        'total': len(entries)
    }), 200
