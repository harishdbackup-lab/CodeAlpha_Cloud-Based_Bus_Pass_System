"""
Database Models for Cloud-Based Bus Pass System
Defines models for buses, routes, passengers, bookings, and tickets
"""

from datetime import datetime, timedelta
import uuid
from enum import Enum
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class BookingStatus(str, Enum):
    """Booking status enumeration"""
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class PaymentStatus(str, Enum):
    """Payment status enumeration"""
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"


class TicketStatus(str, Enum):
    """Ticket status enumeration"""
    ACTIVE = "active"
    USED = "used"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class Route(db.Model):
    """Bus route model"""
    __tablename__ = 'routes'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    route_code = db.Column(db.String(10), unique=True, nullable=False, index=True)
    source = db.Column(db.String(100), nullable=False)
    destination = db.Column(db.String(100), nullable=False)
    distance_km = db.Column(db.Float, nullable=False)
    duration_hours = db.Column(db.Float, nullable=False)
    base_fare = db.Column(db.Float, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    # Relationships
    schedules = db.relationship('Schedule', backref='route', lazy=True, cascade='all, delete-orphan')
    
    def to_dict(self):
        return {
            'id': self.id,
            'route_code': self.route_code,
            'source': self.source,
            'destination': self.destination,
            'distance_km': self.distance_km,
            'duration_hours': self.duration_hours,
            'base_fare': self.base_fare,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat()
        }


class Bus(db.Model):
    """Bus model"""
    __tablename__ = 'buses'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    bus_number = db.Column(db.String(20), unique=True, nullable=False, index=True)
    capacity = db.Column(db.Integer, nullable=False)
    bus_type = db.Column(db.String(50), nullable=False)  # AC, Non-AC, Sleeper, etc.
    registration_number = db.Column(db.String(20), unique=True, nullable=False)
    operator_name = db.Column(db.String(100), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    schedules = db.relationship('Schedule', backref='bus', lazy=True, cascade='all, delete-orphan')
    
    def to_dict(self):
        return {
            'id': self.id,
            'bus_number': self.bus_number,
            'capacity': self.capacity,
            'bus_type': self.bus_type,
            'registration_number': self.registration_number,
            'operator_name': self.operator_name,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat()
        }


class Schedule(db.Model):
    """Bus schedule model (specific date/time)"""
    __tablename__ = 'schedules'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    route_id = db.Column(db.String(36), db.ForeignKey('routes.id'), nullable=False, index=True)
    bus_id = db.Column(db.String(36), db.ForeignKey('buses.id'), nullable=False, index=True)
    departure_time = db.Column(db.DateTime, nullable=False, index=True)
    arrival_time = db.Column(db.DateTime, nullable=False)
    available_seats = db.Column(db.Integer, nullable=False)
    total_seats = db.Column(db.Integer, nullable=False)
    ticket_price = db.Column(db.Float, nullable=False)
    is_cancelled = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    bookings = db.relationship('Booking', backref='schedule', lazy=True, cascade='all, delete-orphan')
    
    def to_dict(self, include_bookings=False):
        data = {
            'id': self.id,
            'route_id': self.route_id,
            'bus_id': self.bus_id,
            'route': self.route.to_dict() if self.route else None,
            'bus': self.bus.to_dict() if self.bus else None,
            'departure_time': self.departure_time.isoformat(),
            'arrival_time': self.arrival_time.isoformat(),
            'available_seats': self.available_seats,
            'total_seats': self.total_seats,
            'occupancy_rate': round((self.total_seats - self.available_seats) / self.total_seats * 100, 2) if self.total_seats > 0 else 0,
            'ticket_price': self.ticket_price,
            'is_cancelled': self.is_cancelled,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }
        
        if include_bookings:
            data['bookings_count'] = len(self.bookings)
        
        return data


class Passenger(db.Model):
    """Passenger model"""
    __tablename__ = 'passengers'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    phone_number = db.Column(db.String(20), unique=True, nullable=False, index=True)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    dob = db.Column(db.Date, nullable=True)
    gender = db.Column(db.String(10), nullable=True)
    government_id = db.Column(db.String(50), nullable=True)  # Aadhar, Passport, etc.
    is_verified = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    bookings = db.relationship('Booking', backref='passenger', lazy=True, cascade='all, delete-orphan')
    payments = db.relationship('Payment', backref='passenger', lazy=True, cascade='all, delete-orphan')
    
    def to_dict(self, include_sensitive=False):
        data = {
            'id': self.id,
            'phone_number': self.phone_number,
            'first_name': self.first_name,
            'last_name': self.last_name,
            'email': self.email,
            'is_verified': self.is_verified,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat()
        }
        
        if include_sensitive:
            data['dob'] = self.dob.isoformat() if self.dob else None
            data['gender'] = self.gender
            data['government_id'] = self.government_id
        
        return data


class Booking(db.Model):
    """Booking model"""
    __tablename__ = 'bookings'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    booking_reference = db.Column(db.String(20), unique=True, nullable=False, index=True)
    schedule_id = db.Column(db.String(36), db.ForeignKey('schedules.id'), nullable=False, index=True)
    passenger_id = db.Column(db.String(36), db.ForeignKey('passengers.id'), nullable=False, index=True)
    number_of_seats = db.Column(db.Integer, nullable=False)
    total_fare = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default=BookingStatus.PENDING.value, index=True)
    booking_time = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    expiry_time = db.Column(db.DateTime, default=lambda: datetime.utcnow() + timedelta(minutes=10))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    payment = db.relationship('Payment', backref='booking', uselist=False, cascade='all, delete-orphan')
    tickets = db.relationship('Ticket', backref='booking', lazy=True, cascade='all, delete-orphan')
    
    def to_dict(self):
        return {
            'id': self.id,
            'booking_reference': self.booking_reference,
            'schedule_id': self.schedule_id,
            'passenger_id': self.passenger_id,
            'number_of_seats': self.number_of_seats,
            'total_fare': self.total_fare,
            'status': self.status,
            'booking_time': self.booking_time.isoformat(),
            'expiry_time': self.expiry_time.isoformat(),
            'schedule': self.schedule.to_dict() if self.schedule else None,
            'payment': self.payment.to_dict() if self.payment else None,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }


class Payment(db.Model):
    """Payment model"""
    __tablename__ = 'payments'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    booking_id = db.Column(db.String(36), db.ForeignKey('bookings.id'), nullable=False, unique=True, index=True)
    passenger_id = db.Column(db.String(36), db.ForeignKey('passengers.id'), nullable=False, index=True)
    amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default=PaymentStatus.PENDING.value, index=True)
    payment_method = db.Column(db.String(50), nullable=False)  # Credit Card, Debit Card, UPI, etc.
    transaction_id = db.Column(db.String(100), unique=True, nullable=True, index=True)
    gateway_response = db.Column(db.Text, nullable=True)
    payment_time = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'booking_id': self.booking_id,
            'passenger_id': self.passenger_id,
            'amount': self.amount,
            'status': self.status,
            'payment_method': self.payment_method,
            'transaction_id': self.transaction_id,
            'payment_time': self.payment_time.isoformat() if self.payment_time else None,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }


class Ticket(db.Model):
    """Ticket model (individual seat)"""
    __tablename__ = 'tickets'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    ticket_number = db.Column(db.String(20), unique=True, nullable=False, index=True)
    booking_id = db.Column(db.String(36), db.ForeignKey('bookings.id'), nullable=False, index=True)
    seat_number = db.Column(db.String(10), nullable=False)
    status = db.Column(db.String(20), default=TicketStatus.ACTIVE.value, index=True)
    qr_code = db.Column(db.Text, nullable=True)  # Base64 encoded QR code
    is_scanned = db.Column(db.Boolean, default=False)
    scan_time = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Unique constraint on booking_id and seat_number
    __table_args__ = (db.UniqueConstraint('booking_id', 'seat_number', name='unique_booking_seat'),)
    
    def to_dict(self):
        return {
            'id': self.id,
            'ticket_number': self.ticket_number,
            'booking_id': self.booking_id,
            'seat_number': self.seat_number,
            'status': self.status,
            'is_scanned': self.is_scanned,
            'scan_time': self.scan_time.isoformat() if self.scan_time else None,
            'created_at': self.created_at.isoformat()
        }


class Refund(db.Model):
    """Refund model"""
    __tablename__ = 'refunds'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    booking_id = db.Column(db.String(36), db.ForeignKey('bookings.id'), nullable=False, index=True)
    payment_id = db.Column(db.String(36), db.ForeignKey('payments.id'), nullable=False, index=True)
    refund_amount = db.Column(db.Float, nullable=False)
    reason = db.Column(db.String(500), nullable=False)
    status = db.Column(db.String(20), default="pending", index=True)  # pending, approved, rejected, completed
    request_time = db.Column(db.DateTime, default=datetime.utcnow)
    processing_time = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'booking_id': self.booking_id,
            'payment_id': self.payment_id,
            'refund_amount': self.refund_amount,
            'reason': self.reason,
            'status': self.status,
            'request_time': self.request_time.isoformat(),
            'processing_time': self.processing_time.isoformat() if self.processing_time else None,
            'created_at': self.created_at.isoformat()
        }


class AuditLog(db.Model):
    """Audit log for all operations"""
    __tablename__ = 'audit_logs'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    action = db.Column(db.String(100), nullable=False, index=True)
    entity_type = db.Column(db.String(50), nullable=False)  # booking, payment, ticket, etc.
    entity_id = db.Column(db.String(36), nullable=False, index=True)
    passenger_id = db.Column(db.String(36), nullable=True, index=True)
    details = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'action': self.action,
            'entity_type': self.entity_type,
            'entity_id': self.entity_id,
            'passenger_id': self.passenger_id,
            'details': self.details,
            'ip_address': self.ip_address,
            'created_at': self.created_at.isoformat()
        }
