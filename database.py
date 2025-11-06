"""
Database module for storing detergent orders and call routing data
Uses PostgreSQL with SQLAlchemy ORM
"""
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Boolean, Numeric, ForeignKey
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from config import Config

# Create base class for models
Base = declarative_base()


class DetergentOrder(Base):
    """Model for detergent orders"""
    __tablename__ = 'detergent_orders'

    id = Column(Integer, primary_key=True, autoincrement=True)
    call_sid = Column(String(100), nullable=False)
    customer_name = Column(String(200), nullable=False)
    customer_phone = Column(String(50), nullable=False)
    customer_email = Column(String(200), nullable=True)  # Email address (optional)
    address_street = Column(String(300), nullable=False)
    address_city = Column(String(100), nullable=False)
    address_state = Column(String(50), nullable=False)  # Changed from 2 to 50 to support full state names
    address_zip = Column(String(10), nullable=False)
    payment_method = Column(String(100), nullable=False)
    quantity = Column(Integer, nullable=False, default=1)  # Number of units ordered

    # QuickBooks sync data
    qb_customer_id = Column(String(50), nullable=True)
    qb_invoice_id = Column(String(50), nullable=True)
    qb_invoice_number = Column(String(50), nullable=True)

    # Sync status: 'pending', 'synced', 'failed'
    sync_status = Column(String(20), nullable=False, default='pending')
    sync_error = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    synced_at = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<DetergentOrder(id={self.id}, name='{self.customer_name}', status='{self.sync_status}')>"


class Department(Base):
    """Model for routing departments (Sales, Support, Billing, etc.)"""
    __tablename__ = 'departments'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False)  # 'Sales', 'Support', 'Billing'
    phone_number = Column(String(20), nullable=False)  # Destination phone (agent or dept line)
    description = Column(Text)  # "Handles new orders and account upgrades"
    active = Column(Boolean, default=True)  # Can be temporarily disabled
    priority = Column(Integer, default=0)  # Display order in menu (higher = first)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<Department(id={self.id}, name='{self.name}', active={self.active})>"


class RoutingRule(Base):
    """Model for keyword-based routing rules"""
    __tablename__ = 'routing_rules'

    id = Column(Integer, primary_key=True, autoincrement=True)
    rule_name = Column(String(100), nullable=False)  # "Order Keywords" or "Support Issues"
    keywords = Column(ARRAY(String), nullable=False)  # ['order', 'purchase', 'buy', 'detergent']
    department_id = Column(Integer, ForeignKey('departments.id'))
    priority = Column(Integer, default=0)  # Higher = checked first
    active = Column(Boolean, default=True)
    match_type = Column(String(20), default='any')  # 'any' or 'all' keywords must match
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship
    department = relationship('Department', backref='routing_rules')

    def __repr__(self):
        return f"<RoutingRule(id={self.id}, name='{self.rule_name}', dept={self.department.name if self.department else 'None'})>"


class CallRoute(Base):
    """Model for logging routing decisions"""
    __tablename__ = 'call_routes'

    id = Column(Integer, primary_key=True, autoincrement=True)
    call_sid = Column(String(100), unique=True, nullable=False)
    caller_phone = Column(String(50))
    routing_decision = Column(String(100))  # Department name chosen
    routing_method = Column(String(50))  # 'ai_analysis', 'keyword_match', 'menu_selection'
    routing_reason = Column(Text)  # Explanation: "Matched keywords: order, purchase"
    confidence_score = Column(Numeric(3, 2))  # AI confidence 0.00-1.00 (NULL for keyword/menu)
    routed_to = Column(String(100))  # Agent phone number or name
    department_id = Column(Integer, ForeignKey('departments.id'))
    routed_at = Column(DateTime)  # When transfer was initiated
    agent_answered_at = Column(DateTime)  # When agent joined conference (NULL if no answer)
    call_ended_at = Column(DateTime)  # When call disconnected
    call_duration_seconds = Column(Integer)  # Total call duration
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationship
    department = relationship('Department', backref='call_routes')

    def __repr__(self):
        return f"<CallRoute(id={self.id}, call_sid='{self.call_sid}', dept='{self.routing_decision}')>"


class CallTranscript(Base):
    """Model for storing conversation transcripts"""
    __tablename__ = 'call_transcripts'

    id = Column(Integer, primary_key=True, autoincrement=True)
    call_sid = Column(String(100), nullable=False)
    speaker = Column(String(20), nullable=False)  # 'caller', 'agent', 'ai'
    text = Column(Text, nullable=False)  # Transcript text
    is_final = Column(Boolean, default=False)  # TRUE for final, FALSE for interim
    confidence = Column(Numeric(3, 2))  # Deepgram confidence score
    timestamp = Column(DateTime, default=datetime.utcnow)
    segment_number = Column(Integer)  # Order in conversation (1, 2, 3...)

    def __repr__(self):
        return f"<CallTranscript(id={self.id}, call_sid='{self.call_sid}', speaker='{self.speaker}', segment={self.segment_number})>"


class CallMetadata(Base):
    """Model for enhanced call tracking and summaries"""
    __tablename__ = 'calls_metadata'

    call_sid = Column(String(100), primary_key=True)
    caller_phone = Column(String(50))
    caller_name = Column(String(200))  # If recognized from QuickBooks
    routing_stage = Column(String(50))  # Current stage: 'greeting', 'routing', 'transferred', 'ended'
    conversation_summary = Column(Text)  # AI-generated summary (generated after call ends)
    outcome = Column(String(50))  # 'routed_successfully', 'no_answer', 'caller_hung_up', 'voicemail'
    call_started_at = Column(DateTime)
    call_ended_at = Column(DateTime)
    total_duration_seconds = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<CallMetadata(call_sid='{self.call_sid}', outcome='{self.outcome}')>"


# Create engine and session
engine = None
Session = None


def init_db():
    """
    Initialize database connection and create tables
    Call this once at startup
    """
    global engine, Session

    if not Config.DATABASE_URL:
        raise ValueError("DATABASE_URL not configured in environment")

    print(f"[Database] Connecting to PostgreSQL...")

    # Create engine
    engine = create_engine(Config.DATABASE_URL, echo=False)

    # Create session factory
    Session = sessionmaker(bind=engine)

    # Create all tables
    Base.metadata.create_all(engine)

    print(f"[Database] ✓ Connected and tables created")
    return engine


def get_session():
    """Get a new database session"""
    if Session is None:
        init_db()
    return Session()


def create_order(order_data):
    """
    Create a new detergent order

    Args:
        order_data: Dict with keys: name, phone, email (optional), address_street, address_city,
                    address_state, address_zip, payment_method, quantity, call_sid

    Returns:
        Order ID
    """
    session = get_session()

    try:
        order = DetergentOrder(
            call_sid=order_data['call_sid'],
            customer_name=order_data['name'],
            customer_phone=order_data['phone'],
            customer_email=order_data.get('email'),  # Optional email field
            address_street=order_data['address_street'],
            address_city=order_data['address_city'],
            address_state=order_data['address_state'],
            address_zip=order_data['address_zip'],
            payment_method=order_data['payment_method'],
            quantity=order_data.get('quantity', 1),  # Default to 1 if not provided
            sync_status='pending'
        )

        session.add(order)
        session.commit()

        order_id = order.id
        print(f"[Database] Created order ID {order_id} for {order_data['name']} - {order_data.get('quantity', 1)} units")

        return order_id

    except Exception as e:
        session.rollback()
        print(f"[Database] Error creating order: {e}")
        raise
    finally:
        session.close()


def update_sync_status(order_id, status, qb_data=None, error=None):
    """
    Update order sync status after QuickBooks sync attempt

    Args:
        order_id: Order ID
        status: 'synced' or 'failed'
        qb_data: Dict with keys: customer_id, invoice_id, invoice_number (if synced)
        error: Error message string (if failed)
    """
    session = get_session()

    try:
        order = session.query(DetergentOrder).filter_by(id=order_id).first()

        if not order:
            print(f"[Database] Order ID {order_id} not found")
            return False

        order.sync_status = status

        if status == 'synced' and qb_data:
            order.qb_customer_id = qb_data.get('customer_id')
            order.qb_invoice_id = qb_data.get('invoice_id')
            order.qb_invoice_number = qb_data.get('invoice_number')
            order.synced_at = datetime.utcnow()
            order.sync_error = None
            print(f"[Database] Order {order_id} marked as synced - Invoice #{qb_data.get('invoice_number')}")

        elif status == 'failed':
            order.sync_error = error
            print(f"[Database] Order {order_id} marked as failed - Error: {error}")

        session.commit()
        return True

    except Exception as e:
        session.rollback()
        print(f"[Database] Error updating order {order_id}: {e}")
        raise
    finally:
        session.close()


def get_pending_orders():
    """
    Get all orders that need syncing (status = 'pending' or 'failed')

    Returns:
        List of DetergentOrder objects
    """
    session = get_session()

    try:
        orders = session.query(DetergentOrder).filter(
            DetergentOrder.sync_status.in_(['pending', 'failed'])
        ).all()

        print(f"[Database] Found {len(orders)} orders needing sync")
        return orders

    except Exception as e:
        print(f"[Database] Error getting pending orders: {e}")
        return []
    finally:
        session.close()


def get_recent_orders(limit=50):
    """
    Get recent orders for dashboard display

    Args:
        limit: Max number of orders to return

    Returns:
        List of DetergentOrder objects
    """
    session = get_session()

    try:
        orders = session.query(DetergentOrder).order_by(
            DetergentOrder.created_at.desc()
        ).limit(limit).all()

        return orders

    except Exception as e:
        print(f"[Database] Error getting recent orders: {e}")
        return []
    finally:
        session.close()


def get_order_by_id(order_id):
    """
    Get a single order by ID

    Args:
        order_id: Order ID

    Returns:
        DetergentOrder object or None
    """
    session = get_session()

    try:
        order = session.query(DetergentOrder).filter_by(id=order_id).first()
        return order
    except Exception as e:
        print(f"[Database] Error getting order {order_id}: {e}")
        return None
    finally:
        session.close()


# ==================== ROUTING FUNCTIONS ====================

def create_call_route(route_data):
    """
    Create a new call routing record

    Args:
        route_data: Dict with keys: call_sid, caller_phone, routing_decision, routing_method,
                    routing_reason, confidence_score, routed_to, department_id, routed_at

    Returns:
        CallRoute ID
    """
    session = get_session()

    try:
        route = CallRoute(
            call_sid=route_data['call_sid'],
            caller_phone=route_data.get('caller_phone'),
            routing_decision=route_data.get('routing_decision'),
            routing_method=route_data.get('routing_method'),
            routing_reason=route_data.get('routing_reason'),
            confidence_score=route_data.get('confidence_score'),
            routed_to=route_data.get('routed_to'),
            department_id=route_data.get('department_id'),
            routed_at=route_data.get('routed_at')
        )

        session.add(route)
        session.commit()

        route_id = route.id
        print(f"[Database] Created call route ID {route_id} for {route_data['call_sid']} -> {route_data.get('routing_decision')}")

        return route_id

    except Exception as e:
        session.rollback()
        print(f"[Database] Error creating call route: {e}")
        raise
    finally:
        session.close()


def create_transcript(call_sid, speaker, text, is_final, confidence=None):
    """
    Create a new transcript entry

    Args:
        call_sid: Call SID
        speaker: 'caller', 'agent', or 'ai'
        text: Transcript text
        is_final: True for final transcript, False for interim
        confidence: Optional confidence score (0.00-1.00)

    Returns:
        Transcript ID
    """
    session = get_session()

    try:
        # Get last segment number for this call
        last_segment = session.query(CallTranscript).filter_by(
            call_sid=call_sid
        ).order_by(CallTranscript.segment_number.desc()).first()

        segment_number = (last_segment.segment_number + 1) if last_segment and last_segment.segment_number else 1

        transcript = CallTranscript(
            call_sid=call_sid,
            speaker=speaker,
            text=text,
            is_final=is_final,
            confidence=confidence,
            segment_number=segment_number
        )

        session.add(transcript)
        session.commit()

        transcript_id = transcript.id

        # Only log final transcripts to avoid spam
        if is_final:
            print(f"[Database] Transcript {transcript_id}: {speaker} (segment {segment_number})")

        return transcript_id

    except Exception as e:
        session.rollback()
        print(f"[Database] Error creating transcript: {e}")
        raise
    finally:
        session.close()


def get_call_transcripts(call_sid, final_only=True):
    """
    Get all transcripts for a call

    Args:
        call_sid: Call SID
        final_only: If True, return only final transcripts (default)

    Returns:
        List of CallTranscript objects
    """
    session = get_session()

    try:
        query = session.query(CallTranscript).filter_by(call_sid=call_sid)

        if final_only:
            query = query.filter_by(is_final=True)

        transcripts = query.order_by(CallTranscript.timestamp).all()
        return transcripts

    except Exception as e:
        print(f"[Database] Error getting transcripts for {call_sid}: {e}")
        return []
    finally:
        session.close()


def update_call_route_end(call_sid, agent_answered_at=None, call_ended_at=None, call_duration_seconds=None):
    """
    Update call route record when call ends

    Args:
        call_sid: Call SID
        agent_answered_at: When agent joined conference (optional)
        call_ended_at: When call disconnected (optional)
        call_duration_seconds: Total call duration (optional)

    Returns:
        True if successful, False otherwise
    """
    session = get_session()

    try:
        route = session.query(CallRoute).filter_by(call_sid=call_sid).first()

        if not route:
            print(f"[Database] Call route not found for {call_sid}")
            return False

        if agent_answered_at:
            route.agent_answered_at = agent_answered_at
        if call_ended_at:
            route.call_ended_at = call_ended_at
        if call_duration_seconds is not None:
            route.call_duration_seconds = call_duration_seconds

        session.commit()
        print(f"[Database] Updated call route for {call_sid}")
        return True

    except Exception as e:
        session.rollback()
        print(f"[Database] Error updating call route {call_sid}: {e}")
        return False
    finally:
        session.close()


if __name__ == "__main__":
    # Test database connection and table creation
    print("Testing database connection...")
    init_db()
    print("Database initialized successfully!")
