from flask import Blueprint, request, jsonify
from extensions import db
from models.notification import Notification
from services.auth_service import jwt_required

notifications_bp = Blueprint('notifications_bp', __name__)

@notifications_bp.route('', methods=['GET'])
@jwt_required
def list_notifications():
    user = request.current_user
    notifications = Notification.query.filter_by(user_id=user.id).order_by(Notification.created_at.desc()).limit(50).all()
    unread_count = Notification.query.filter_by(user_id=user.id, is_read=False).count()
    return jsonify({
        'notifications': [n.to_dict() for n in notifications],
        'unread_count': unread_count
    }), 200

@notifications_bp.route('/<int:notif_id>/read', methods=['PUT'])
@jwt_required
def mark_notification_read(notif_id):
    user = request.current_user
    notif = Notification.query.filter_by(id=notif_id, user_id=user.id).first()
    if notif:
        notif.is_read = True
        db.session.commit()
    return jsonify({'message': 'Marked as read'}), 200

@notifications_bp.route('/read-all', methods=['POST'])
@jwt_required
def mark_all_read():
    user = request.current_user
    Notification.query.filter_by(user_id=user.id, is_read=False).update({'is_read': True})
    db.session.commit()
    return jsonify({'message': 'All notifications marked as read'}), 200
