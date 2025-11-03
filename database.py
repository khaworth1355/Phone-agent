"""
Database module for storing detergent orders
Uses PostgreSQL with SQLAlchemy ORM
"""
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
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
    address_street = Column(String(300), nullable=False)
    address_city = Column(String(100), nullable=False)
    address_state = Column(String(2), nullable=False)
    address_zip = Column(String(10), nullable=False)
    payment_method = Column(String(100), nullable=False)

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
        order_data: Dict with keys: name, phone, address_street, address_city,
                    address_state, address_zip, payment_method, call_sid

    Returns:
        Order ID
    """
    session = get_session()

    try:
        order = DetergentOrder(
            call_sid=order_data['call_sid'],
            customer_name=order_data['name'],
            customer_phone=order_data['phone'],
            address_street=order_data['address_street'],
            address_city=order_data['address_city'],
            address_state=order_data['address_state'],
            address_zip=order_data['address_zip'],
            payment_method=order_data['payment_method'],
            sync_status='pending'
        )

        session.add(order)
        session.commit()

        order_id = order.id
        print(f"[Database] Created order ID {order_id} for {order_data['name']}")

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


if __name__ == "__main__":
    # Test database connection and table creation
    print("Testing database connection...")
    init_db()
    print("Database initialized successfully!")
