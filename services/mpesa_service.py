import base64
import requests
import json
import uuid
from datetime import datetime
from flask import current_app
from extensions import db
from models.transaction import Transaction
from models.payment import Payment
from models.events import DeliveryEvent
from services.ledger_service import record_ledger_entry
from services.notification_service import send_notification

def format_phone_number(phone):
    """Normalize phone to Kenya Daraja format 254XXXXXXXXX"""
    phone = phone.strip().replace(' ', '').replace('-', '').replace('+', '')
    if phone.startswith('0'):
        phone = '254' + phone[1:]
    elif phone.startswith('7') or phone.startswith('1'):
        phone = '254' + phone
    return phone

def get_daraja_access_token():
    consumer_key = current_app.config.get('MPESA_CONSUMER_KEY')
    consumer_secret = current_app.config.get('MPESA_CONSUMER_SECRET')
    
    if not consumer_key or not consumer_secret:
        return None
        
    api_url = "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
    try:
        response = requests.get(api_url, auth=(consumer_key, consumer_secret), timeout=10)
        if response.status_code == 200:
            return response.json().get('access_token')
    except Exception as e:
        current_app.logger.error(f"Error fetching Daraja token: {e}")
    return None

def initiate_mpesa_stk_push(transaction_id, user_id, phone_number, amount):
    """
    Initiates STK Push via Safaricom Daraja or Sandbox Simulator if credentials absent.
    """
    tx = Transaction.query.get(transaction_id)
    if not tx:
        return False, "Transaction not found", None
        
    formatted_phone = format_phone_number(phone_number)
    token = get_daraja_access_token()
    
    # Check if real Daraja credentials are fully configured
    if token and current_app.config.get('MPESA_PASSKEY'):
        # Real Daraja STK Push
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        shortcode = current_app.config.get('MPESA_SHORTCODE', '174379')
        passkey = current_app.config.get('MPESA_PASSKEY')
        password = base64.b64encode(f"{shortcode}{passkey}{timestamp}".encode('utf-8')).decode('utf-8')
        
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        payload = {
            "BusinessShortCode": shortcode,
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": int(round(amount)),
            "PartyA": formatted_phone,
            "PartyB": shortcode,
            "PhoneNumber": formatted_phone,
            "CallBackURL": current_app.config.get('MPESA_CALLBACK_URL'),
            "AccountReference": tx.reference[:12],
            "TransactionDesc": f"Escrow {tx.reference[:10]}"
        }
        
        try:
            req_url = "https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest"
            res = requests.post(req_url, json=payload, headers=headers, timeout=15)
            data = res.json()
            if res.status_code == 200 and data.get('ResponseCode') == '0':
                checkout_id = data.get('CheckoutRequestID')
                payment = Payment(
                    transaction_id=tx.id,
                    user_id=user_id,
                    amount=amount,
                    currency='KES',
                    provider='mpesa_daraja',
                    checkout_request_id=checkout_id,
                    merchant_request_id=data.get('MerchantRequestID'),
                    phone_number=formatted_phone,
                    status='pending'
                )
                db.session.add(payment)
                db.session.commit()
                return True, "STK push prompt sent to your phone. Enter M-Pesa PIN to complete payment.", payment.to_dict()
            else:
                return False, data.get('ResponseDescription', 'STK Push initiation failed'), None
        except Exception as e:
            current_app.logger.error(f"Daraja STK push error: {e}")
            # Fallback to simulated flow if network fails or mock mode is requested
            
    # Simulated Daraja Adapter
    checkout_id = f"ws_CO_{datetime.utcnow().strftime('%d%m%Y%H%M%S')}_{uuid.uuid4().hex[:6]}"
    payment = Payment(
        transaction_id=tx.id,
        user_id=user_id,
        amount=amount,
        currency='KES',
        provider='mpesa_sandbox_simulator',
        checkout_request_id=checkout_id,
        merchant_request_id=f"MR_{uuid.uuid4().hex[:8].upper()}",
        phone_number=formatted_phone,
        status='pending'
    )
    db.session.add(payment)
    db.session.commit()
    
    return True, "Simulated M-Pesa STK Push initiated. You can verify payment instantly via the sandbox prompt.", payment.to_dict()

def process_mpesa_callback(callback_data):
    """
    Processes official Safaricom Daraja STK Push Callback JSON.
    Guarantees duplicate callback protection & idempotent state transitions.
    """
    body = callback_data.get('Body', {}).get('stkCallback', {})
    checkout_request_id = body.get('CheckoutRequestID')
    result_code = body.get('ResultCode')
    result_desc = body.get('ResultDesc')
    
    if not checkout_request_id:
        return False, "Missing CheckoutRequestID in callback"
        
    payment = Payment.query.filter_by(checkout_request_id=checkout_request_id).first()
    if not payment:
        return False, "Payment matching CheckoutRequestID not found"
        
    # Duplicate callback check (idempotency)
    if payment.status in ['completed', 'failed']:
        return True, "Callback already processed (idempotent)."
        
    payment.raw_callback = json.dumps(callback_data)
    
    if result_code == 0:
        # Success
        meta_items = body.get('CallbackMetadata', {}).get('Item', [])
        receipt = None
        for item in meta_items:
            if item.get('Name') == 'MpesaReceiptNumber':
                receipt = item.get('Value')
                
        payment.status = 'completed'
        payment.mpesa_receipt_number = receipt or f"MPE-{uuid.uuid4().hex[:8].upper()}"
        payment.completed_at = datetime.utcnow()
        
        # Transition transaction to payment_held
        tx = payment.transaction
        tx.status = 'payment_held'
        
        # Record double-entry escrow ledger
        record_ledger_entry(
            user_id=payment.user_id,
            transaction_id=tx.id,
            entry_type='escrow_deposit',
            amount=payment.amount,
            direction='credit',
            description=f"M-Pesa deposit for Escrow Deal {tx.reference} ({payment.mpesa_receipt_number})",
            provider='Safaricom M-Pesa'
        )
        
        DeliveryEvent.log(
            transaction_id=tx.id,
            event_type='payment_verified',
            description=f"M-Pesa payment of KES {payment.amount:,.2f} verified ({payment.mpesa_receipt_number}). Funds secured in Escrow Vault.",
            actor_id=payment.user_id
        )
        
        send_notification(
            tx.seller_id,
            "Payment Secured in Escrow!",
            f"Buyer deposited KES {payment.amount:,.2f} for '{tx.title}'. Please prepare the order for dispatch.",
            f"/transactions/{tx.reference}"
        )
        send_notification(
            tx.buyer_id,
            "Payment Confirmed",
            f"Your payment of KES {payment.amount:,.2f} is safely held in Escrow protection.",
            f"/transactions/{tx.reference}"
        )
        
        db.session.commit()
        return True, "Payment successfully verified and funds secured in escrow."
    else:
        # Failed or cancelled by user
        payment.status = 'failed'
        payment.failure_reason = result_desc or "Payment cancelled by user"
        db.session.commit()
        return False, f"Payment failed: {result_desc}"

def simulate_complete_payment(checkout_request_id):
    """
    Sandbox helper to complete a simulated STK push without needing Safaricom webhook connectivity.
    """
    mock_receipt = f"QHK{datetime.utcnow().strftime('%y%m%d')}{secrets_token(4).upper()}"
    mock_callback = {
        "Body": {
            "stkCallback": {
                "MerchantRequestID": f"MR_{uuid.uuid4().hex[:8]}",
                "CheckoutRequestID": checkout_request_id,
                "ResultCode": 0,
                "ResultDesc": "The service request is processed successfully.",
                "CallbackMetadata": {
                    "Item": [
                        {"Name": "Amount", "Value": 1000},
                        {"Name": "MpesaReceiptNumber", "Value": mock_receipt},
                        {"Name": "TransactionDate", "Value": int(datetime.utcnow().strftime('%Y%m%d%H%M%S'))},
                        {"Name": "PhoneNumber", "Value": 254712345678}
                    ]
                }
            }
        }
    }
    return process_mpesa_callback(mock_callback)

def secrets_token(n):
    import secrets
    return secrets.token_hex(n)
