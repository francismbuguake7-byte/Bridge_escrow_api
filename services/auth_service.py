import jwt
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify, current_app
from models.user import User

def generate_token(user_id, role):
    payload = {
        'user_id': user_id,
        'role': role,
        'exp': datetime.utcnow() + current_app.config['JWT_ACCESS_TOKEN_EXPIRES'],
        'iat': datetime.utcnow()
    }
    return jwt.encode(payload, current_app.config['JWT_SECRET_KEY'], algorithm='HS256')

def decode_token(token):
    try:
        payload = jwt.decode(token, current_app.config['JWT_SECRET_KEY'], algorithms=['HS256'])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

def jwt_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Authorization token required'}), 401
        
        token = auth_header.split(' ')[1]
        payload = decode_token(token)
        if not payload:
            return jsonify({'error': 'Invalid or expired token'}), 401
        
        user = User.query.get(payload['user_id'])
        if not user or not user.is_active:
            return jsonify({'error': 'User not found or account deactivated'}), 401
        
        request.current_user = user
        return f(*args, **kwargs)
    return decorated

def role_required(allowed_roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not hasattr(request, 'current_user'):
                return jsonify({'error': 'Authentication required'}), 401
            
            user = request.current_user
            if user.role not in allowed_roles:
                return jsonify({
                    'error': f"Access forbidden. Required role: {', '.join(allowed_roles)}. Your role: {user.role}"
                }), 403
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator
