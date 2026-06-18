"""
Flask REST API for Cloud-Based Bus Pass System
Main application file with all API endpoints
"""

import os
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, request, jsonify
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from werkzeug.security import generate_password_hash, check_password_hash

from models import db, Passenger, Route, Bus, Schedule, Booking, Ticket, Payment, AuditLog
from booking_service import BookingService, TicketService, ScheduleService
from payment_service import PaymentService, PriceCalculator

# Initialize Flask app
app = Flask(__name__)

# Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///bus_pass.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', 'bus_system_secret_key_2024')
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=24)

# Initialize extensions
db.init_app(app)
jwt = JWTManager(app)

# Create tables
with app.app_context():
    db.create_all()


# ==================== HEALTH CHECK ====================

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'service': 'Cloud-Based Bus Pass System'
    }), 200


# ==================== AUTHENTICATION ====================

@app.route('/api/auth/register', methods=['POST'])
def register():
    """
    Register a new passenger
    
    JSON:
    {
        "phone_number": "9876543210",
        "first_name": "John",
        "last_name": "Doe",
        "email": "john@example.com",
        "password": "securepassword123"
    }
    """
    try:
        data = request.get_json()
        
        # Validate input
        required_fields = ['phone_number', 'first_name', 'last_name', 'email', 'password']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'error': f'{field} is required'}), 400
        
        # Check if passenger already exists
        if Passenger.query.filter_by(phone_number=data['phone_number']).first():
            return jsonify({'error': 'Phone number already registered'}), 409
        
        if Passenger.query.filter_by(email=data['email']).first():
            return jsonify({'error': 'Email already registered'}), 409
        
        # Create passenger
        passenger = Passenger(
            phone_number=data['phone_number'],
            first_name=data['first_name'],
            last_name=data['last_name'],
            email=data['email'],
            password_hash=generate_password_hash(data['password']),
            is_verified=False,
            is_active=True
        )
        
        db.session.add(passenger)
        db.session.commit()
        
        return jsonify({
            'message': 'Registration successful',
            'passenger_id': passenger.id,
            'email': passenger.email
        }), 201
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/api/auth/login', methods=['POST'])
def login():
    """
    Login passenger and get JWT token
    
    JSON:
    {
        "email": "john@example.com",
        "password": "securepassword123"
    }
    """
    try:
        data = request.get_json()
        
        email = data.get('email')
        password = data.get('password')
        
        if not email or not password:
            return jsonify({'error': 'Email and password required'}), 400
        
        passenger = Passenger.query.filter_by(email=email).first()
        
        if not passenger or not check_password_hash(passenger.password_hash, password):
            return jsonify({'error': 'Invalid credentials'}), 401
        
        if not passenger.is_active:
            return jsonify({'error': 'Account is inactive'}), 403
        
        # Generate JWT token
        access_token = create_access_token(identity=passenger.id)
        
        return jsonify({
            'message': 'Login successful',
            'access_token': access_token,
            'passenger_id': passenger.id,
            'first_name': passenger.first_name,
            'last_name': passenger.last_name,
            'email': passenger.email
        }), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ==================== SEARCH & BROWSE ====================

@app.route('/api/search/schedules', methods=['GET'])
def search_schedules():
    """
    Search for available bus schedules
    
    Query params:
    - source: Source city
    - destination: Destination city
    - date: Travel date (YYYY-MM-DD)
    - sort_by: departure_time or price (optional)
    """
    try:
        source = request.args.get('source')
        destination = request.args.get('destination')
        date = request.args.get('date')
        
        if not all([source, destination, date]):
            return jsonify({'error': 'source, destination, and date are required'}), 400
        
        # Search schedules
        schedules = ScheduleService.search_schedules(source, destination, date)
        
        return jsonify({
            'search_criteria': {
                'source': source,
                'destination': destination,
                'date': date
            },
            'total_results': len(schedules),
            'schedules': schedules
        }), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/schedules/<schedule_id>', methods=['GET'])
def get_schedule(schedule_id):
    """Get schedule details"""
    try:
        schedule = ScheduleService.get_schedule_details(schedule_id)
        if not schedule:
            return jsonify({'error': 'Schedule not found'}), 404
        
        return jsonify(schedule), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/routes', methods=['GET'])
def get_routes():
    """Get all available routes"""
    try:
        routes = Route.query.filter_by(is_active=True).all()
        return jsonify({
            'total_routes': len(routes),
            'routes': [route.to_dict() for route in routes]
        }), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ==================== BOOKING ====================

@app.route('/api/bookings/create', methods=['POST'])
@jwt_required()
def create_booking():
    """
    Create a new booking
    
    JSON:
    {
        "schedule_id": "...",
        "num_seats": 2
    }
    """
    try:
        passenger_id = get_jwt_identity()
        data = request.get_json()
        
        schedule_id = data.get('schedule_id')
        num_seats = data.get('num_seats', 1)
        
        if not schedule_id:
            return jsonify({'error': 'schedule_id is required'}), 400
        
        result = BookingService.create_booking(schedule_id, passenger_id, num_seats)
        
        if not result['success']:
            return jsonify({'error': result['error']}), 400
        
        return jsonify(result), 201
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/api/bookings/<booking_id>', methods=['GET'])
@jwt_required()
def get_booking(booking_id):
    """Get booking details"""
    try:
        passenger_id = get_jwt_identity()
        booking = Booking.query.filter_by(id=booking_id, passenger_id=passenger_id).first()
        
        if not booking:
            return jsonify({'error': 'Booking not found'}), 404
        
        return jsonify(booking.to_dict()), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/bookings/my-bookings', methods=['GET'])
@jwt_required()
def get_my_bookings():
    """Get all bookings for current passenger"""
    try:
        passenger_id = get_jwt_identity()
        bookings = BookingService.get_passenger_bookings(passenger_id)
        
        return jsonify({
            'total_bookings': len(bookings),
            'bookings': bookings
        }), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/bookings/<booking_id>/cancel', methods=['POST'])
@jwt_required()
def cancel_booking(booking_id):
    """Cancel a booking"""
    try:
        passenger_id = get_jwt_identity()
        booking = Booking.query.filter_by(id=booking_id, passenger_id=passenger_id).first()
        
        if not booking:
            return jsonify({'error': 'Booking not found'}), 404
        
        reason = request.get_json().get('reason', 'Passenger requested') if request.is_json else 'Passenger requested'
        
        result = BookingService.cancel_booking(booking_id, reason)
        
        if not result['success']:
            return jsonify({'error': result['error']}), 400
        
        return jsonify(result), 200
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ==================== PAYMENT ====================

@app.route('/api/payments/initiate', methods=['POST'])
@jwt_required()
def initiate_payment():
    """
    Initiate payment for a booking
    
    JSON:
    {
        "booking_id": "...",
        "payment_method": "credit_card"
    }
    """
    try:
        passenger_id = get_jwt_identity()
        data = request.get_json()
        
        booking_id = data.get('booking_id')
        payment_method = data.get('payment_method', 'credit_card')
        
        if not booking_id:
            return jsonify({'error': 'booking_id is required'}), 400
        
        # Verify booking belongs to passenger
        booking = Booking.query.filter_by(id=booking_id, passenger_id=passenger_id).first()
        if not booking:
            return jsonify({'error': 'Booking not found'}), 404
        
        result = PaymentService.initiate_payment(booking_id, booking.total_fare, payment_method)
        
        if not result['success']:
            return jsonify({'error': result['error']}), 400
        
        return jsonify(result), 200
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/api/payments/<payment_id>/process', methods=['POST'])
@jwt_required()
def process_payment(payment_id):
    """
    Process payment after gateway response
    
    JSON:
    {
        "transaction_id": "TXN123456",
        "gateway_response": {...}
    }
    """
    try:
        passenger_id = get_jwt_identity()
        data = request.get_json()
        
        transaction_id = data.get('transaction_id')
        gateway_response = data.get('gateway_response')
        
        if not transaction_id:
            return jsonify({'error': 'transaction_id is required'}), 400
        
        # Verify payment belongs to passenger
        payment = Payment.query.filter_by(id=payment_id, passenger_id=passenger_id).first()
        if not payment:
            return jsonify({'error': 'Payment not found'}), 404
        
        result = PaymentService.process_payment(payment_id, transaction_id, gateway_response)
        
        if not result['success']:
            return jsonify({'error': result['error']}), 400
        
        return jsonify(result), 200
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/api/payments/<payment_id>', methods=['GET'])
@jwt_required()
def get_payment(payment_id):
    """Get payment details"""
    try:
        passenger_id = get_jwt_identity()
        payment = Payment.query.filter_by(id=payment_id, passenger_id=passenger_id).first()
        
        if not payment:
            return jsonify({'error': 'Payment not found'}), 404
        
        return jsonify(payment.to_dict()), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ==================== TICKETS ====================

@app.route('/api/tickets/<ticket_id>', methods=['GET'])
@jwt_required()
def get_ticket(ticket_id):
    """Get ticket details"""
    try:
        ticket = TicketService.get_ticket(ticket_id)
        if not ticket:
            return jsonify({'error': 'Ticket not found'}), 404
        
        return jsonify(ticket), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/bookings/<booking_id>/tickets', methods=['GET'])
@jwt_required()
def get_booking_tickets(booking_id):
    """Get tickets for a booking"""
    try:
        passenger_id = get_jwt_identity()
        booking = Booking.query.filter_by(id=booking_id, passenger_id=passenger_id).first()
        
        if not booking:
            return jsonify({'error': 'Booking not found'}), 404
        
        tickets = TicketService.get_booking_tickets(booking_id)
        
        return jsonify({
            'booking_id': booking_id,
            'total_tickets': len(tickets),
            'tickets': tickets
        }), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/tickets/scan', methods=['POST'])
def scan_ticket():
    """
    Scan ticket at boarding point
    
    JSON:
    {
        "ticket_number": "TKT..."
    }
    """
    try:
        data = request.get_json()
        ticket_number = data.get('ticket_number')
        
        if not ticket_number:
            return jsonify({'error': 'ticket_number is required'}), 400
        
        result = TicketService.scan_ticket(ticket_number)
        
        if not result['success']:
            return jsonify({'error': result['error']}), 400
        
        return jsonify(result), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ==================== PRICING ====================

@app.route('/api/pricing/calculate', methods=['POST'])
def calculate_price():
    """
    Calculate dynamic price
    
    JSON:
    {
        "base_fare": 500,
        "occupancy_rate": 75,
        "days_before_departure": 5,
        "promo_code": "WELCOME10"
    }
    """
    try:
        data = request.get_json()
        
        base_fare = data.get('base_fare')
        occupancy_rate = data.get('occupancy_rate', 50)
        days_before = data.get('days_before_departure', 7)
        promo_code = data.get('promo_code')
        
        if not base_fare:
            return jsonify({'error': 'base_fare is required'}), 400
        
        # Calculate dynamic price
        dynamic_price = PriceCalculator.calculate_dynamic_price(
            base_fare, occupancy_rate, days_before
        )
        
        result = {
            'base_fare': base_fare,
            'dynamic_price': dynamic_price,
            'occupancy_rate': occupancy_rate,
            'days_before_departure': days_before
        }
        
        # Apply promo code if provided
        if promo_code:
            final_price, discount, promo_info = PriceCalculator.apply_promo_code(dynamic_price, promo_code)
            result['promo_code'] = promo_info
            result['final_price'] = final_price
            result['total_discount'] = discount
        else:
            result['final_price'] = dynamic_price
        
        return jsonify(result), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ==================== ADMIN ENDPOINTS ====================

@app.route('/api/admin/schedules/create', methods=['POST'])
def create_schedule():
    """Create a new schedule (admin only)"""
    try:
        data = request.get_json()
        
        # Verify admin (in production, use proper authentication)
        admin_key = request.headers.get('X-Admin-Key')
        if admin_key != os.getenv('ADMIN_KEY', 'admin_secret_2024'):
            return jsonify({'error': 'Unauthorized'}), 403
        
        # Create schedule
        schedule = Schedule(
            route_id=data.get('route_id'),
            bus_id=data.get('bus_id'),
            departure_time=datetime.fromisoformat(data.get('departure_time')),
            arrival_time=datetime.fromisoformat(data.get('arrival_time')),
            ticket_price=data.get('ticket_price'),
            available_seats=data.get('total_seats'),
            total_seats=data.get('total_seats')
        )
        
        db.session.add(schedule)
        db.session.commit()
        
        return jsonify({
            'message': 'Schedule created',
            'schedule_id': schedule.id
        }), 201
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/api/admin/buses/create', methods=['POST'])
def create_bus():
    """Create a new bus (admin only)"""
    try:
        data = request.get_json()
        
        admin_key = request.headers.get('X-Admin-Key')
        if admin_key != os.getenv('ADMIN_KEY', 'admin_secret_2024'):
            return jsonify({'error': 'Unauthorized'}), 403
        
        bus = Bus(
            bus_number=data.get('bus_number'),
            capacity=data.get('capacity'),
            bus_type=data.get('bus_type'),
            registration_number=data.get('registration_number'),
            operator_name=data.get('operator_name')
        )
        
        db.session.add(bus)
        db.session.commit()
        
        return jsonify({
            'message': 'Bus created',
            'bus_id': bus.id
        }), 201
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/api/admin/routes/create', methods=['POST'])
def create_route():
    """Create a new route (admin only)"""
    try:
        data = request.get_json()
        
        admin_key = request.headers.get('X-Admin-Key')
        if admin_key != os.getenv('ADMIN_KEY', 'admin_secret_2024'):
            return jsonify({'error': 'Unauthorized'}), 403
        
        route = Route(
            route_code=data.get('route_code'),
            source=data.get('source'),
            destination=data.get('destination'),
            distance_km=data.get('distance_km'),
            duration_hours=data.get('duration_hours'),
            base_fare=data.get('base_fare')
        )
        
        db.session.add(route)
        db.session.commit()
        
        return jsonify({
            'message': 'Route created',
            'route_id': route.id
        }), 201
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ==================== ERROR HANDLERS ====================

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404


@app.errorhandler(500)
def server_error(error):
    return jsonify({'error': 'Internal server error'}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
