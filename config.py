import os
from datetime import timedelta

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'bridge-escrow-dev-super-secret-key-2026')
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', 'jwt-dev-secret-token-key-2026')
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(days=7)
    
    # SQLite default, postgresql compatible
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL', 
        f"sqlite:///{os.path.join(BASE_DIR, 'bridge_escrow.db')}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Platform Escrow Fees
    ESCROW_FEE_PERCENTAGE = float(os.environ.get('ESCROW_FEE_PERCENTAGE', 0.025))  # 2.5%
    ESCROW_MIN_FEE = float(os.environ.get('ESCROW_MIN_FEE', 50.0))  # KES 50 min
    
    # Daraja M-Pesa Credentials (can be configured via environment)
    MPESA_ENV = os.environ.get('MPESA_ENV', 'sandbox')  # 'sandbox' or 'production'
    MPESA_CONSUMER_KEY = os.environ.get('MPESA_CONSUMER_KEY', '')
    MPESA_CONSUMER_SECRET = os.environ.get('MPESA_CONSUMER_SECRET', '')
    MPESA_PASSKEY = os.environ.get('MPESA_PASSKEY', '')
    MPESA_SHORTCODE = os.environ.get('MPESA_SHORTCODE', '174379')
    MPESA_CALLBACK_URL = os.environ.get('MPESA_CALLBACK_URL', 'http://localhost:5000/api/payments/mpesa/callback')
    
    # Verification Code Settings
    CODE_EXPIRY_HOURS = int(os.environ.get('CODE_EXPIRY_HOURS', 48))
    MAX_VERIFICATION_ATTEMPTS = int(os.environ.get('MAX_VERIFICATION_ATTEMPTS', 3))

class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    SECRET_KEY = 'test-secret-key'
    JWT_SECRET_KEY = 'test-jwt-secret'
