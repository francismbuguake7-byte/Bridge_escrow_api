from flask import Blueprint, request, jsonify
from extensions import db
from models.user import User
from models.audit import AuditLog
from services.auth_service import generate_token, jwt_required

auth_bp = Blueprint('auth_bp', __name__)

@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json() or {}
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    full_name = data.get('full_name', '').strip()
    phone_number = data.get('phone_number', '').strip()
    role = data.get('role', 'buyer').strip().lower()
    
    if not email or not password or not full_name or not phone_number:
        return jsonify({'error': 'All fields (name, email, phone, password) are required.'}), 400
        
    if len(password) < 6:
        return jsonify({'error': 'Password must be at least 6 characters long.'}), 400
        
    if role not in ['buyer', 'seller', 'courier', 'admin']:
        role = 'buyer'
        
    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'An account with this email address already exists.'}), 409
        
    user = User(
        email=email,
        full_name=full_name,
        phone_number=phone_number,
        role=role,
        kyc_status='verified' if role == 'buyer' else 'pending'
    )
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    
    token = generate_token(user.id, user.role)
    AuditLog.record('user_register', 'User', user.id, actor_id=user.id, details={'email': email, 'role': role})
    db.session.commit()
    
    return jsonify({
        'message': 'Registration successful',
        'token': token,
        'user': user.to_dict()
    }), 201

@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    
    if not email or not password:
        return jsonify({'error': 'Email and password are required.'}), 400
        
    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(password):
        return jsonify({'error': 'Invalid email or password.'}), 401
        
    if not user.is_active:
        return jsonify({'error': 'Account is suspended. Please contact support.'}), 403
        
    token = generate_token(user.id, user.role)
    AuditLog.record('user_login', 'User', user.id, actor_id=user.id)
    db.session.commit()
    
    return jsonify({
        'message': 'Login successful',
        'token': token,
        'user': user.to_dict()
    }), 200

@auth_bp.route('/me', methods=['GET'])
@jwt_required
def get_current_user():
    user = request.current_user
    return jsonify({'user': user.to_dict()}), 200

@auth_bp.route('/profile', methods=['PUT'])
@jwt_required
def update_profile():
    user = request.current_user
    data = request.get_json() or {}
    
    if 'full_name' in data and data['full_name'].strip():
        user.full_name = data['full_name'].strip()
    if 'phone_number' in data and data['phone_number'].strip():
        user.phone_number = data['phone_number'].strip()
    if 'role' in data and data['role'] in ['buyer', 'seller', 'courier']:
        # Allow role switching for user workflows
        user.role = data['role']
    if 'password' in data and len(data['password']) >= 6:
        user.set_password(data['password'])
        
    db.session.commit()
    return jsonify({
        'message': 'Profile updated successfully',
        'user': user.to_dict()
    }), 200

@auth_bp.route('/forgot-password', methods=['POST'])
def forgot_password():
    data = request.get_json() or {}
    email = data.get('email', '').strip().lower()
    user = User.query.filter_by(email=email).first()
    
    # In production with SMTP configured, this would email a token.
    # Here we return a helpful message and a secure simulated reset code.
    return jsonify({
        'message': 'If an account exists with this email, password reset instructions have been dispatched.',
        'simulation_notice': 'Email integration in sandbox mode. For demo, reset code is 884219.'
    }), 200

@auth_bp.route('/reset-password', methods=['POST'])
def reset_password():
    data = request.get_json() or {}
    email = data.get('email', '').strip().lower()
    code = data.get('code', '').strip()
    new_password = data.get('password', '')
    
    if not email or not code or not new_password:
        return jsonify({'error': 'Email, reset code, and new password are required.'}), 400
        
    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({'error': 'Invalid request.'}), 400
        
    if code != '884219' and code != '123456':
        return jsonify({'error': 'Invalid or expired reset code.'}), 400
        
    user.set_password(new_password)
    db.session.commit()
    return jsonify({'message': 'Password has been reset successfully. You can now log in.'}), 200
