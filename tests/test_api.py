import pytest
import json
from config import TestConfig
from app import create_app
from extensions import db
from models.user import User
from models.transaction import Transaction
from models.verification import VerificationCode
from models.dispute import Dispute
from models.ledger import LedgerEntry
from services.verification_service import verify_pickup, verify_handover
from services.escrow_service import buyer_accept_and_release, raise_dispute, resolve_dispute_by_admin
from services.mpesa_service import simulate_complete_payment

@pytest.fixture
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def auth_tokens(client):
    # Register buyer, seller, courier, admin
    buyer_res = client.post('/api/auth/register', json={
        'email': 'testbuyer@bridgeescrow.co.ke',
        'password': 'Password123!',
        'full_name': 'Test Buyer',
        'phone_number': '+254711000111',
        'role': 'buyer'
    })
    seller_res = client.post('/api/auth/register', json={
        'email': 'testseller@bridgeescrow.co.ke',
        'password': 'Password123!',
        'full_name': 'Test Seller',
        'phone_number': '+254711000222',
        'role': 'seller'
    })
    courier_res = client.post('/api/auth/register', json={
        'email': 'testcourier@bridgeescrow.co.ke',
        'password': 'Password123!',
        'full_name': 'Test Courier',
        'phone_number': '+254711000333',
        'role': 'courier'
    })
    admin_res = client.post('/api/auth/register', json={
        'email': 'testadmin@bridgeescrow.co.ke',
        'password': 'AdminSecret123!',
        'full_name': 'Test Admin',
        'phone_number': '+254711000444',
        'role': 'admin'
    })
    
    return {
        'buyer': buyer_res.get_json()['token'],
        'seller': seller_res.get_json()['token'],
        'courier': courier_res.get_json()['token'],
        'admin': admin_res.get_json()['token'],
        'buyer_id': buyer_res.get_json()['user']['id'],
        'seller_id': seller_res.get_json()['user']['id'],
        'courier_id': courier_res.get_json()['user']['id'],
        'admin_id': admin_res.get_json()['user']['id']
    }

def test_auth_registration_and_login(client):
    # Valid login
    res = client.post('/api/auth/login', json={
        'email': 'testbuyer@bridgeescrow.co.ke',
        'password': 'Password123!'
    })
    # Will fail if not yet registered, let's register directly
    reg = client.post('/api/auth/register', json={
        'email': 'newuser@bridgeescrow.co.ke',
        'password': 'Password123!',
        'full_name': 'New User',
        'phone_number': '+254700000000',
        'role': 'buyer'
    })
    assert reg.status_code == 201
    assert 'token' in reg.get_json()
    
    # Login with right password
    login_res = client.post('/api/auth/login', json={
        'email': 'newuser@bridgeescrow.co.ke',
        'password': 'Password123!'
    })
    assert login_res.status_code == 200
    
    # Login with wrong password
    bad_login = client.post('/api/auth/login', json={
        'email': 'newuser@bridgeescrow.co.ke',
        'password': 'WrongPassword!'
    })
    assert bad_login.status_code == 401

def test_transaction_creation_and_fee_calculation(client, auth_tokens):
    headers = {'Authorization': f"Bearer {auth_tokens['buyer']}"}
    create_res = client.post('/api/transactions', headers=headers, json={
        'title': 'MacBook Pro 14 M2',
        'description': '512GB space gray mint condition',
        'category': 'goods_electronics',
        'amount': 150000,
        'delivery_fee': 500,
        'delivery_type': 'courier',
        'seller': 'testseller@bridgeescrow.co.ke',
        'inspection_period_days': 3
    })
    assert create_res.status_code == 201
    data = create_res.get_json()['transaction']
    assert data['amount'] == 150000
    # Platform fee is 2.5% = 3750
    assert data['platform_fee'] == 3750
    assert data['delivery_fee'] == 500
    assert data['total_amount'] == 154250
    assert data['status'] == 'draft'

def test_terms_acceptance_and_mpesa_payment_flow(client, auth_tokens):
    buyer_h = {'Authorization': f"Bearer {auth_tokens['buyer']}"}
    seller_h = {'Authorization': f"Bearer {auth_tokens['seller']}"}
    
    # 1. Create Deal
    create_res = client.post('/api/transactions', headers=buyer_h, json={
        'title': 'Sony Camera A7 IV',
        'description': 'Full frame camera body with 28-70mm lens',
        'category': 'goods_electronics',
        'amount': 220000,
        'delivery_fee': 800,
        'delivery_type': 'courier',
        'seller': 'testseller@bridgeescrow.co.ke'
    })
    ref = create_res.get_json()['transaction']['reference']
    
    # 2. Seller accepts terms
    accept_res = client.post(f'/api/transactions/{ref}/accept-terms', headers=seller_h)
    assert accept_res.status_code == 200
    assert accept_res.get_json()['transaction']['status'] == 'pending_payment'
    
    # 3. Buyer initiates M-Pesa STK push
    pay_res = client.post('/api/payments/initiate', headers=buyer_h, json={
        'transaction_ref': ref,
        'phone_number': '0711000111'
    })
    assert pay_res.status_code == 200
    checkout_id = pay_res.get_json()['payment']['checkout_request_id']
    
    # 4. Simulate confirmation
    conf_res = client.post('/api/payments/simulate-confirm', headers=buyer_h, json={
        'checkout_request_id': checkout_id
    })
    assert conf_res.status_code == 200
    assert conf_res.get_json()['transaction_status'] == 'payment_held'
    
    # 5. Idempotent check (re-submitting same callback shouldn't error or double charge)
    conf_res2 = client.post('/api/payments/simulate-confirm', headers=buyer_h, json={
        'checkout_request_id': checkout_id
    })
    assert conf_res2.status_code == 200

def test_dual_code_verification_system(client, auth_tokens):
    buyer_h = {'Authorization': f"Bearer {auth_tokens['buyer']}"}
    seller_h = {'Authorization': f"Bearer {auth_tokens['seller']}"}
    courier_h = {'Authorization': f"Bearer {auth_tokens['courier']}"}
    
    # Create and advance transaction to payment_held
    create_res = client.post('/api/transactions', headers=buyer_h, json={
        'title': 'PlayStation 5 Console',
        'description': 'Disc edition with 2 dualsense controllers',
        'amount': 65000,
        'delivery_fee': 500,
        'seller': 'testseller@bridgeescrow.co.ke'
    })
    ref = create_res.get_json()['transaction']['reference']
    client.post(f'/api/transactions/{ref}/accept-terms', headers=seller_h)
    pay = client.post('/api/payments/initiate', headers=buyer_h, json={'transaction_ref': ref})
    client.post('/api/payments/simulate-confirm', headers=buyer_h, json={
        'checkout_request_id': pay.get_json()['payment']['checkout_request_id']
    })
    
    # Seller marks ready
    client.post(f'/api/transactions/{ref}/mark-ready', headers=seller_h)
    
    # Seller retrieves 6-digit pickup code
    pickup_res = client.get(f'/api/transactions/{ref}/pickup-code', headers=seller_h)
    assert pickup_res.status_code == 200
    pickup_code = pickup_res.get_json()['code']
    assert len(pickup_code) == 6
    
    # Buyer CANNOT retrieve pickup code (authorized seller only)
    bad_pick = client.get(f'/api/transactions/{ref}/pickup-code', headers=buyer_h)
    assert bad_pick.status_code == 400
    
    # Courier enters WRONG pickup code
    bad_verify = client.post('/api/delivery/verify-pickup', headers=courier_h, json={
        'transaction_ref': ref,
        'code': '000000'
    })
    assert bad_verify.status_code == 400
    assert 'remaining' in bad_verify.get_json()['error']
    
    # Courier enters CORRECT pickup code
    good_pickup = client.post('/api/delivery/verify-pickup', headers=courier_h, json={
        'transaction_ref': ref,
        'code': pickup_code
    })
    assert good_pickup.status_code == 200
    assert good_pickup.get_json()['transaction_status'] == 'in_transit'
    
    # REPLAY PREVENTION: Pickup code cannot be reused!
    replay_pickup = client.post('/api/delivery/verify-pickup', headers=courier_h, json={
        'transaction_ref': ref,
        'code': pickup_code
    })
    assert replay_pickup.status_code == 400
    
    # Buyer retrieves handover code
    handover_res = client.get(f'/api/transactions/{ref}/handover-code', headers=buyer_h)
    assert handover_res.status_code == 200
    handover_code = handover_res.get_json()['code']
    assert len(handover_code) == 6
    
    # INTERCHANGE PREVENTION: Courier cannot use handover code as pickup code or vice versa
    cross_check = client.post('/api/delivery/verify-pickup', headers=courier_h, json={
        'transaction_ref': ref,
        'code': handover_code
    })
    assert cross_check.status_code == 400
    
    # Courier enters handover code upon physical drop-off
    good_handover = client.post('/api/delivery/verify-handover', headers=courier_h, json={
        'transaction_ref': ref,
        'code': handover_code
    })
    assert good_handover.status_code == 200
    
    # CRITICAL CHECK: Courier handover must NOT release funds!
    # Status must be 'in_inspection', NOT 'completed'
    assert good_handover.get_json()['transaction_status'] == 'in_inspection'
    
    # Buyer inspects and accepts goods -> Releases funds
    release_res = client.post(f'/api/transactions/{ref}/accept-and-release', headers=buyer_h)
    assert release_res.status_code == 200
    assert release_res.get_json()['transaction']['status'] == 'completed'

def test_dispute_blocks_funds_release_and_admin_resolves(client, auth_tokens):
    buyer_h = {'Authorization': f"Bearer {auth_tokens['buyer']}"}
    seller_h = {'Authorization': f"Bearer {auth_tokens['seller']}"}
    admin_h = {'Authorization': f"Bearer {auth_tokens['admin']}"}
    
    # Create deal and pay
    create_res = client.post('/api/transactions', headers=buyer_h, json={
        'title': 'Drone DJI Mini 4 Pro',
        'description': 'Fly more combo with RC2 controller',
        'amount': 120000,
        'delivery_fee': 500,
        'seller': 'testseller@bridgeescrow.co.ke'
    })
    ref = create_res.get_json()['transaction']['reference']
    client.post(f'/api/transactions/{ref}/accept-terms', headers=seller_h)
    pay = client.post('/api/payments/initiate', headers=buyer_h, json={'transaction_ref': ref})
    client.post('/api/payments/simulate-confirm', headers=buyer_h, json={
        'checkout_request_id': pay.get_json()['payment']['checkout_request_id']
    })
    
    # Buyer raises dispute
    disp_res = client.post(f'/api/transactions/{ref}/dispute', headers=buyer_h, json={
        'reason': 'damaged_goods',
        'description': 'Camera gimbal arrived cracked and unresponsive to calibration.'
    })
    assert disp_res.status_code == 200
    assert disp_res.get_json()['transaction']['status'] == 'disputed'
    
    # Funds CANNOT be released while active dispute is open
    release_try = client.post(f'/api/transactions/{ref}/accept-and-release', headers=buyer_h)
    assert release_try.status_code == 400
    assert 'locked due to an active dispute' in release_try.get_json()['error']
    
    # Admin inspects disputes
    disputes_list = client.get('/api/admin/disputes', headers=admin_h)
    assert disputes_list.status_code == 200
    dispute_id = disputes_list.get_json()['disputes'][0]['id']
    
    # Admin issues resolution (refund buyer)
    resolve_res = client.post(f'/api/admin/disputes/{dispute_id}/resolve', headers=admin_h, json={
        'resolution': 'resolved_buyer_refund',
        'notes': 'Inspection photos verified factory box was damaged and gimbal motor burned out.'
    })
    assert resolve_res.status_code == 200
    
    # Non-admin cannot access admin stats
    unauth_admin = client.get('/api/admin/stats', headers=buyer_h)
    assert unauth_admin.status_code == 403
