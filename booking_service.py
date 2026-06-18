"""
Booking Management Service
Handles ticket booking, reservation, and cancellation logic
"""

import uuid
from datetime import datetime, timedelta
import secrets
from models import (
    db, Route, Bus, Schedule, Booking, Ticket, Payment, Refund, AuditLog,
    BookingStatus, PaymentStatus, TicketStatus
)


class BookingService:
    """Service for managing bus bookings"""
    
    BOOKING_EXPIRY_MINUTES = 10  # Booking expires after 10 minutes without payment
    CANCELLATION_CHARGE_PERCENTAGE = 10  # 10% cancellation charge
    
    @staticmethod
    def generate_booking_reference():
        """Generate unique booking reference"""
        return f"BUS{uuid.uuid4().hex[:8].upper()}"
    
    @staticmethod
    def generate_ticket_number():
        """Generate unique ticket number"""
        return f"TKT{uuid.uuid4().hex[:10].upper()}"
    
    @staticmethod
    def validate_booking_request(schedule_id: str, num_seats: int, passenger_id: str):
        """
        Validate booking request
        
        Returns:
            tuple: (is_valid, error_message, schedule)
        """
        # Validate schedule exists
        schedule = Schedule.query.filter_by(id=schedule_id).first()
        if not schedule:
            return False, "Schedule not found", None
        
        # Check if schedule is cancelled
        if schedule.is_cancelled:
            return False, "This schedule has been cancelled", None
        
        # Check departure time is in future
        if schedule.departure_time <= datetime.utcnow():
            return False, "Cannot book for past schedules", None
        
        # Check seat availability
        if schedule.available_seats < num_seats:
            return False, f"Only {schedule.available_seats} seats available", None
        
        # Maximum seats per booking
        if num_seats > 6:
            return False, "Maximum 6 seats per booking", None
        
        if num_seats < 1:
            return False, "Minimum 1 seat required", None
        
        return True, "Valid", schedule
    
    @staticmethod
    def create_booking(schedule_id: str, passenger_id: str, num_seats: int):
        """
        Create a new booking
        
        Returns:
            dict: Booking details or error message
        """
        # Validate booking request
        is_valid, error_msg, schedule = BookingService.validate_booking_request(
            schedule_id, num_seats, passenger_id
        )
        
        if not is_valid:
            return {'success': False, 'error': error_msg}
        
        try:
            # Reserve seats (atomic operation)
            booking_reference = BookingService.generate_booking_reference()
            total_fare = schedule.ticket_price * num_seats
            
            # Create booking
            booking = Booking(
                booking_reference=booking_reference,
                schedule_id=schedule_id,
                passenger_id=passenger_id,
                number_of_seats=num_seats,
                total_fare=total_fare,
                status=BookingStatus.PENDING.value,
                expiry_time=datetime.utcnow() + timedelta(minutes=BookingService.BOOKING_EXPIRY_MINUTES)
            )
            
            # Decrease available seats
            schedule.available_seats -= num_seats
            schedule.updated_at = datetime.utcnow()
            
            db.session.add(booking)
            db.session.commit()
            
            # Log action
            AuditLog.log_action(
                action='booking_created',
                entity_type='booking',
                entity_id=booking.id,
                passenger_id=passenger_id,
                details=f"Created booking for {num_seats} seats"
            )
            
            return {
                'success': True,
                'booking_id': booking.id,
                'booking_reference': booking.booking_reference,
                'total_fare': total_fare,
                'expiry_time': booking.expiry_time.isoformat(),
                'message': 'Booking created. Complete payment within 10 minutes.'
            }
        
        except Exception as e:
            db.session.rollback()
            return {'success': False, 'error': f'Booking failed: {str(e)}'}
    
    @staticmethod
    def confirm_booking(booking_id: str, payment_status: str = PaymentStatus.COMPLETED.value):
        """
        Confirm a booking after payment
        
        Returns:
            dict: Confirmation details
        """
        try:
            booking = Booking.query.filter_by(id=booking_id).first()
            if not booking:
                return {'success': False, 'error': 'Booking not found'}
            
            if booking.status != BookingStatus.PENDING.value:
                return {'success': False, 'error': f'Booking is already {booking.status}'}
            
            # Check if payment is completed
            payment = Payment.query.filter_by(booking_id=booking_id).first()
            if not payment or payment.status != PaymentStatus.COMPLETED.value:
                return {'success': False, 'error': 'Payment not completed'}
            
            # Update booking status
            booking.status = BookingStatus.CONFIRMED.value
            booking.updated_at = datetime.utcnow()
            
            # Generate tickets for each seat
            for i in range(booking.number_of_seats):
                ticket = Ticket(
                    ticket_number=BookingService.generate_ticket_number(),
                    booking_id=booking_id,
                    seat_number=f"SEAT_{i + 1}",  # In real system, get from bus seat map
                    status=TicketStatus.ACTIVE.value
                )
                db.session.add(ticket)
            
            db.session.commit()
            
            # Log action
            AuditLog.log_action(
                action='booking_confirmed',
                entity_type='booking',
                entity_id=booking_id,
                passenger_id=booking.passenger_id,
                details='Booking confirmed after successful payment'
            )
            
            return {
                'success': True,
                'booking_id': booking_id,
                'booking_reference': booking.booking_reference,
                'status': booking.status,
                'tickets_issued': booking.number_of_seats,
                'message': 'Booking confirmed. Tickets issued.'
            }
        
        except Exception as e:
            db.session.rollback()
            return {'success': False, 'error': f'Confirmation failed: {str(e)}'}
    
    @staticmethod
    def cancel_booking(booking_id: str, reason: str = "User requested"):
        """
        Cancel a booking
        
        Returns:
            dict: Cancellation details
        """
        try:
            booking = Booking.query.filter_by(id=booking_id).first()
            if not booking:
                return {'success': False, 'error': 'Booking not found'}
            
            if booking.status == BookingStatus.CANCELLED.value:
                return {'success': False, 'error': 'Booking is already cancelled'}
            
            if booking.status == BookingStatus.COMPLETED.value:
                return {'success': False, 'error': 'Cannot cancel completed booking'}
            
            # Calculate refund amount
            refund_amount = booking.total_fare
            
            # Apply cancellation charge if booking is confirmed
            if booking.status == BookingStatus.CONFIRMED.value:
                # Check if departure is more than 4 hours away
                if booking.schedule.departure_time > datetime.utcnow() + timedelta(hours=4):
                    charge = booking.total_fare * (BookingService.CANCELLATION_CHARGE_PERCENTAGE / 100)
                    refund_amount -= charge
                else:
                    # Non-refundable if cancelled within 4 hours
                    refund_amount = 0
            
            # Update booking status
            booking.status = BookingStatus.CANCELLED.value
            booking.updated_at = datetime.utcnow()
            
            # Release seats back to schedule
            booking.schedule.available_seats += booking.number_of_seats
            booking.schedule.updated_at = datetime.utcnow()
            
            # Create refund record
            if booking.payment:
                refund = Refund(
                    booking_id=booking_id,
                    payment_id=booking.payment.id,
                    refund_amount=refund_amount,
                    reason=reason,
                    status="completed"
                )
                db.session.add(refund)
            
            # Cancel all tickets
            for ticket in booking.tickets:
                ticket.status = TicketStatus.CANCELLED.value
            
            db.session.commit()
            
            # Log action
            AuditLog.log_action(
                action='booking_cancelled',
                entity_type='booking',
                entity_id=booking_id,
                passenger_id=booking.passenger_id,
                details=f'Cancelled with refund: {refund_amount}'
            )
            
            return {
                'success': True,
                'booking_id': booking_id,
                'original_amount': booking.total_fare,
                'refund_amount': refund_amount,
                'cancellation_charge': booking.total_fare - refund_amount,
                'message': 'Booking cancelled successfully'
            }
        
        except Exception as e:
            db.session.rollback()
            return {'success': False, 'error': f'Cancellation failed: {str(e)}'}
    
    @staticmethod
    def get_booking_details(booking_id: str):
        """Get booking details"""
        booking = Booking.query.filter_by(id=booking_id).first()
        if not booking:
            return None
        return booking.to_dict()
    
    @staticmethod
    def get_passenger_bookings(passenger_id: str):
        """Get all bookings for a passenger"""
        bookings = Booking.query.filter_by(passenger_id=passenger_id).order_by(
            Booking.created_at.desc()
        ).all()
        return [booking.to_dict() for booking in bookings]


class TicketService:
    """Service for managing tickets"""
    
    @staticmethod
    def get_ticket(ticket_id: str):
        """Get ticket details"""
        ticket = Ticket.query.filter_by(id=ticket_id).first()
        if not ticket:
            return None
        return ticket.to_dict()
    
    @staticmethod
    def scan_ticket(ticket_number: str):
        """
        Scan ticket at boarding point
        
        Returns:
            dict: Scan result
        """
        try:
            ticket = Ticket.query.filter_by(ticket_number=ticket_number).first()
            if not ticket:
                return {'success': False, 'error': 'Ticket not found'}
            
            if ticket.status == TicketStatus.CANCELLED.value:
                return {'success': False, 'error': 'Ticket is cancelled'}
            
            if ticket.is_scanned:
                return {'success': False, 'error': 'Ticket already scanned'}
            
            # Mark ticket as scanned
            ticket.is_scanned = True
            ticket.scan_time = datetime.utcnow()
            ticket.status = TicketStatus.USED.value
            
            db.session.commit()
            
            # Log action
            AuditLog.log_action(
                action='ticket_scanned',
                entity_type='ticket',
                entity_id=ticket.id,
                details=f'Ticket scanned for seat {ticket.seat_number}'
            )
            
            return {
                'success': True,
                'ticket_number': ticket_number,
                'seat_number': ticket.seat_number,
                'booking_reference': ticket.booking.booking_reference,
                'passenger_name': f"{ticket.booking.passenger.first_name} {ticket.booking.passenger.last_name}",
                'message': 'Ticket validated successfully'
            }
        
        except Exception as e:
            db.session.rollback()
            return {'success': False, 'error': f'Scan failed: {str(e)}'}
    
    @staticmethod
    def get_booking_tickets(booking_id: str):
        """Get all tickets for a booking"""
        tickets = Ticket.query.filter_by(booking_id=booking_id).all()
        return [ticket.to_dict() for ticket in tickets]


class ScheduleService:
    """Service for managing bus schedules"""
    
    @staticmethod
    def search_schedules(source: str, destination: str, date_str: str):
        """
        Search for available schedules
        
        Args:
            source: Source city
            destination: Destination city
            date_str: Date in YYYY-MM-DD format
        
        Returns:
            list: Available schedules
        """
        try:
            from datetime import datetime as dt
            search_date = dt.strptime(date_str, '%Y-%m-%d').date()
            search_start = datetime(search_date.year, search_date.month, search_date.day)
            search_end = search_start + timedelta(days=1)
            
            # Find routes
            routes = Route.query.filter(
                Route.source.ilike(f"%{source}%"),
                Route.destination.ilike(f"%{destination}%"),
                Route.is_active == True
            ).all()
            
            if not routes:
                return []
            
            route_ids = [route.id for route in routes]
            
            # Find schedules for these routes
            schedules = Schedule.query.filter(
                Schedule.route_id.in_(route_ids),
                Schedule.departure_time >= search_start,
                Schedule.departure_time < search_end,
                Schedule.is_cancelled == False,
                Schedule.available_seats > 0
            ).order_by(Schedule.departure_time).all()
            
            return [schedule.to_dict(include_bookings=True) for schedule in schedules]
        
        except Exception as e:
            return []
    
    @staticmethod
    def get_schedule_details(schedule_id: str):
        """Get schedule details"""
        schedule = Schedule.query.filter_by(id=schedule_id).first()
        if not schedule:
            return None
        return schedule.to_dict(include_bookings=True)


class AuditLog:
    """Helper for audit logging"""
    
    @staticmethod
    def log_action(action: str, entity_type: str, entity_id: str, 
                   passenger_id: str = None, details: str = None, ip_address: str = None):
        """Log an action"""
        try:
            log = AuditLog(
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                passenger_id=passenger_id,
                details=details,
                ip_address=ip_address
            )
            db.session.add(log)
            db.session.commit()
        except Exception as e:
            print(f"Failed to log action: {str(e)}")
