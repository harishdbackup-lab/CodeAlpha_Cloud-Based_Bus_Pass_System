"""
Payment Processing Service
Handles payment processing, validation, and security
"""

from datetime import datetime
from models import db, Payment, Booking, AuditLog, PaymentStatus, BookingStatus
import hashlib
import hmac


class PaymentService:
    """Service for managing payments"""
    
    # Simulated payment gateway configuration
    GATEWAY_SECRET = "payment_secret_key_2024"
    
    @staticmethod
    def initiate_payment(booking_id: str, amount: float, payment_method: str):
        """
        Initiate payment for a booking
        
        Args:
            booking_id: Booking ID
            amount: Payment amount
            payment_method: Payment method (Credit Card, Debit Card, UPI, etc.)
        
        Returns:
            dict: Payment initiation details
        """
        try:
            # Validate booking
            booking = Booking.query.filter_by(id=booking_id).first()
            if not booking:
                return {'success': False, 'error': 'Booking not found'}
            
            # Check booking is still pending
            if booking.status != BookingStatus.PENDING.value:
                return {'success': False, 'error': 'Booking is not pending'}
            
            # Validate amount
            if abs(amount - booking.total_fare) > 0.01:  # Allow small floating point differences
                return {'success': False, 'error': f'Amount mismatch. Expected {booking.total_fare}, got {amount}'}
            
            # Check if payment already exists
            existing_payment = Payment.query.filter_by(booking_id=booking_id).first()
            if existing_payment and existing_payment.status == PaymentStatus.COMPLETED.value:
                return {'success': False, 'error': 'Booking already paid'}
            
            # Create or update payment record
            if existing_payment:
                payment = existing_payment
                payment.status = PaymentStatus.PENDING.value
            else:
                payment = Payment(
                    booking_id=booking_id,
                    passenger_id=booking.passenger_id,
                    amount=amount,
                    payment_method=payment_method,
                    status=PaymentStatus.PENDING.value
                )
                db.session.add(payment)
            
            db.session.commit()
            
            # Generate payment reference
            payment_reference = PaymentService.generate_payment_reference(payment.id)
            
            # Log action
            AuditLog.log_action(
                action='payment_initiated',
                entity_type='payment',
                entity_id=payment.id,
                passenger_id=booking.passenger_id,
                details=f'Payment initiated for {amount} via {payment_method}'
            )
            
            return {
                'success': True,
                'payment_id': payment.id,
                'payment_reference': payment_reference,
                'amount': amount,
                'payment_method': payment_method,
                'message': 'Payment initiated. Proceed to gateway.'
            }
        
        except Exception as e:
            db.session.rollback()
            return {'success': False, 'error': f'Payment initiation failed: {str(e)}'}
    
    @staticmethod
    def process_payment(payment_id: str, transaction_id: str, gateway_response: dict = None):
        """
        Process payment after gateway response
        
        Args:
            payment_id: Payment ID
            transaction_id: Transaction ID from gateway
            gateway_response: Response from payment gateway
        
        Returns:
            dict: Payment processing result
        """
        try:
            payment = Payment.query.filter_by(id=payment_id).first()
            if not payment:
                return {'success': False, 'error': 'Payment not found'}
            
            # Validate transaction
            if not PaymentService.validate_transaction(transaction_id, payment.amount):
                payment.status = PaymentStatus.FAILED.value
                db.session.commit()
                return {'success': False, 'error': 'Transaction validation failed'}
            
            # Update payment status
            payment.status = PaymentStatus.COMPLETED.value
            payment.transaction_id = transaction_id
            payment.payment_time = datetime.utcnow()
            if gateway_response:
                import json
                payment.gateway_response = json.dumps(gateway_response)
            
            # Update booking status to confirmed
            booking = payment.booking
            booking.status = BookingStatus.CONFIRMED.value
            booking.updated_at = datetime.utcnow()
            
            db.session.commit()
            
            # Log action
            AuditLog.log_action(
                action='payment_completed',
                entity_type='payment',
                entity_id=payment_id,
                passenger_id=payment.passenger_id,
                details=f'Payment completed. Transaction: {transaction_id}'
            )
            
            return {
                'success': True,
                'payment_id': payment_id,
                'booking_id': booking.id,
                'transaction_id': transaction_id,
                'amount': payment.amount,
                'status': 'completed',
                'message': 'Payment successful. Booking confirmed.'
            }
        
        except Exception as e:
            db.session.rollback()
            return {'success': False, 'error': f'Payment processing failed: {str(e)}'}
    
    @staticmethod
    def validate_transaction(transaction_id: str, amount: float) -> bool:
        """
        Validate transaction with payment gateway
        (Simulated - in production, call actual gateway)
        
        Returns:
            bool: Transaction is valid
        """
        # In production, this would call the actual payment gateway API
        # For now, we simulate successful validation
        
        # Check transaction format
        if not transaction_id or len(transaction_id) < 10:
            return False
        
        # Check amount is positive
        if amount <= 0:
            return False
        
        # Simulate gateway validation
        # In production: call gateway.validate_transaction(transaction_id, amount)
        return True
    
    @staticmethod
    def generate_payment_reference(payment_id: str) -> str:
        """Generate payment reference"""
        reference = f"PAY{payment_id[:8].upper()}{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        return reference
    
    @staticmethod
    def process_refund(booking_id: str, refund_amount: float, reason: str = "Passenger requested"):
        """
        Process refund for a booking
        
        Returns:
            dict: Refund processing result
        """
        try:
            booking = Booking.query.filter_by(id=booking_id).first()
            if not booking:
                return {'success': False, 'error': 'Booking not found'}
            
            payment = Payment.query.filter_by(booking_id=booking_id).first()
            if not payment:
                return {'success': False, 'error': 'Payment not found'}
            
            if payment.status != PaymentStatus.COMPLETED.value:
                return {'success': False, 'error': 'Payment not completed'}
            
            # Validate refund amount
            if refund_amount > payment.amount:
                return {'success': False, 'error': 'Refund amount exceeds paid amount'}
            
            # Process refund
            payment.status = PaymentStatus.REFUNDED.value
            payment.updated_at = datetime.utcnow()
            
            db.session.commit()
            
            # Log action
            AuditLog.log_action(
                action='payment_refunded',
                entity_type='payment',
                entity_id=payment.id,
                passenger_id=payment.passenger_id,
                details=f'Refund processed: {refund_amount}. Reason: {reason}'
            )
            
            return {
                'success': True,
                'booking_id': booking_id,
                'payment_id': payment.id,
                'refund_amount': refund_amount,
                'original_amount': payment.amount,
                'message': 'Refund processed successfully'
            }
        
        except Exception as e:
            db.session.rollback()
            return {'success': False, 'error': f'Refund processing failed: {str(e)}'}
    
    @staticmethod
    def verify_payment_signature(payment_id: str, signature: str) -> bool:
        """
        Verify payment signature for security
        
        Returns:
            bool: Signature is valid
        """
        # Create expected signature
        message = f"{payment_id}:{PaymentService.GATEWAY_SECRET}"
        expected_signature = hmac.new(
            PaymentService.GATEWAY_SECRET.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(signature, expected_signature)
    
    @staticmethod
    def get_payment_details(payment_id: str):
        """Get payment details"""
        payment = Payment.query.filter_by(id=payment_id).first()
        if not payment:
            return None
        return payment.to_dict()


class PriceCalculator:
    """Calculate ticket prices with dynamic pricing"""
    
    @staticmethod
    def calculate_dynamic_price(base_fare: float, occupancy_rate: float, 
                               days_before_departure: int) -> float:
        """
        Calculate dynamic price based on occupancy and time
        
        Args:
            base_fare: Base ticket price
            occupancy_rate: Occupancy percentage (0-100)
            days_before_departure: Days until departure
        
        Returns:
            float: Calculated price
        """
        # Occupancy-based surge pricing
        occupancy_multiplier = 1.0
        if occupancy_rate > 80:
            occupancy_multiplier = 1.5  # 50% increase when >80% full
        elif occupancy_rate > 60:
            occupancy_multiplier = 1.25  # 25% increase when >60% full
        
        # Time-based pricing
        time_multiplier = 1.0
        if days_before_departure < 2:
            time_multiplier = 1.3  # 30% increase for last-minute bookings
        elif days_before_departure > 30:
            time_multiplier = 0.85  # 15% discount for advance bookings
        
        final_price = base_fare * occupancy_multiplier * time_multiplier
        return round(final_price, 2)
    
    @staticmethod
    def apply_promo_code(price: float, promo_code: str) -> tuple:
        """
        Apply promotional code discount
        
        Returns:
            tuple: (discounted_price, discount_amount, promo_details)
        """
        promo_discounts = {
            'WELCOME10': 0.10,  # 10% off
            'SUMMER15': 0.15,   # 15% off
            'FRIEND20': 0.20,   # 20% off
            'STUDENT25': 0.25,  # 25% off
        }
        
        discount_rate = promo_discounts.get(promo_code.upper(), 0)
        
        if discount_rate == 0:
            return price, 0, None
        
        discount_amount = price * discount_rate
        final_price = price - discount_amount
        
        return round(final_price, 2), round(discount_amount, 2), {
            'promo_code': promo_code.upper(),
            'discount_percentage': discount_rate * 100,
            'discount_amount': round(discount_amount, 2)
        }
