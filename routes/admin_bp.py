from flask import Blueprint, request, jsonify
from extensions import db
from models.user import User
from models.transaction import Transaction
from models.dispute import Dispute
from models.payment import Payment
from models.audit import AuditLog
from services.auth_service import jwt_required, role_required
from services.escrow_service import resolve_dispute_by_admin

admin_bp = Blueprint('admin_bp', __name__)

@admin_bp.route('/stats', methods=['GET'])
@jwt_required
@role_required(['admin'])
def get_admin_stats():
    total_users = User.query.count()
    total_transactions = Transaction.query.count()
    
    # Escrow Volume (sum of completed or active transactions)
    total_volume = db.session.query(db.func.sum(Transaction.amount)).scalar() or 0.0
    
    # Active Escrow Held (statuses: payment_held, order_prepared, in_transit, delivered, in_inspection, disputed)
    active_escrow = db.session.query(db.func.sum(Transaction.amount)).filter(
        Transaction.status.in_(['payment_held', 'order_prepared', 'in_transit', 'delivered', 'in_inspection', 'disputed'])
    ).scalar() or 0.0
    
    # Platform fees earned
    platform_revenue = db.session.query(db.func.sum(Transaction.platform_fee)).filter_by(status='completed').scalar() or 0.0
    
    # Disputes
    open_disputes = Dispute.query.filter(Dispute.status.in_(['open', 'under_review'])).count()
    total_disputes = Dispute.query.count()
    dispute_rate = round((total_disputes / total_transactions * 100), 1) if total_transactions > 0 else 0.0
    
    # Payments
    total_payments = Payment.query.count()
    successful_payments = Payment.query.filter_by(status='completed').count()
    reconciliation_rate = round((successful_payments / total_payments * 100), 1) if total_payments > 0 else 100.0
    
    # Couriers
    active_couriers = User.query.filter_by(role='courier', is_active=True).count()
    
    return jsonify({
        'stats': {
            'total_users': total_users,
            'total_transactions': total_transactions,
            'total_volume': round(total_volume, 2),
            'active_escrow_holding': round(active_escrow, 2),
            'platform_revenue': round(platform_revenue, 2),
            'open_disputes': open_disputes,
            'dispute_rate': dispute_rate,
            'reconciliation_rate': reconciliation_rate,
            'active_couriers': active_couriers
        }
    }), 200

@admin_bp.route('/users', methods=['GET'])
@jwt_required
@role_required(['admin'])
def list_admin_users():
    users = User.query.order_by(User.created_at.desc()).all()
    return jsonify({'users': [u.to_dict() for u in users]}), 200

@admin_bp.route('/users/<int:user_id>/status', methods=['PUT'])
@jwt_required
@role_required(['admin'])
def update_user_status(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
        
    data = request.get_json() or {}
    if 'kyc_status' in data:
        user.kyc_status = data['kyc_status']
    if 'is_active' in data:
        user.is_active = bool(data['is_active'])
    if 'role' in data and data['role'] in ['buyer', 'seller', 'courier', 'admin']:
        user.role = data['role']
        
    AuditLog.record(
        action='update_user_status',
        target_type='User',
        target_id=user.id,
        actor_id=request.current_user.id,
        details=data
    )
    db.session.commit()
    return jsonify({'message': 'User updated successfully', 'user': user.to_dict()}), 200

@admin_bp.route('/transactions', methods=['GET'])
@jwt_required
@role_required(['admin'])
def list_admin_transactions():
    transactions = Transaction.query.order_by(Transaction.created_at.desc()).all()
    return jsonify({'transactions': [t.to_dict() for t in transactions]}), 200

@admin_bp.route('/disputes', methods=['GET'])
@jwt_required
@role_required(['admin'])
def list_admin_disputes():
    disputes = Dispute.query.order_by(Dispute.created_at.desc()).all()
    results = []
    for d in disputes:
        item = d.to_dict()
        item['transaction'] = d.transaction.to_dict() if d.transaction else None
        results.append(item)
    return jsonify({'disputes': results}), 200

@admin_bp.route('/disputes/<int:dispute_id>/resolve', methods=['POST'])
@jwt_required
@role_required(['admin'])
def resolve_dispute(dispute_id):
    admin = request.current_user
    data = request.get_json() or {}
    resolution = data.get('resolution')  # resolved_buyer_refund, resolved_seller_payout, resolved_split, rejected
    notes = data.get('notes', '').strip()
    
    if not resolution or not notes:
        return jsonify({'error': 'Resolution ruling and detailed notes are required.'}), 400
        
    success, msg = resolve_dispute_by_admin(dispute_id, admin.id, resolution, notes)
    if not success:
        return jsonify({'error': msg}), 400
        
    return jsonify({'message': msg}), 200

@admin_bp.route('/payments', methods=['GET'])
@jwt_required
@role_required(['admin'])
def list_admin_payments():
    payments = Payment.query.order_by(Payment.created_at.desc()).all()
    results = []
    for p in payments:
        item = p.to_dict()
        item['transaction_ref'] = p.transaction.reference if p.transaction else None
        results.append(item)
    return jsonify({'payments': results}), 200

@admin_bp.route('/audit-logs', methods=['GET'])
@jwt_required
@role_required(['admin'])
def list_audit_logs():
    logs = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(100).all()
    return jsonify({'audit_logs': [l.to_dict() for l in logs]}), 200
