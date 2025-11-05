"""
Migration script to add customer_email column to detergent_orders table
Run this once to update your existing database schema
"""
from sqlalchemy import create_engine, text
from config import Config

def add_email_column():
    """Add customer_email column to detergent_orders table"""

    if not Config.DATABASE_URL:
        print("❌ DATABASE_URL not configured")
        return False

    print(f"[Migration] Connecting to database...")
    engine = create_engine(Config.DATABASE_URL, echo=False)

    try:
        with engine.connect() as conn:
            # Check if column already exists
            check_query = text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name='detergent_orders'
                AND column_name='customer_email'
            """)

            result = conn.execute(check_query)
            if result.fetchone():
                print("[Migration] ✓ customer_email column already exists")
                return True

            # Add the column
            print("[Migration] Adding customer_email column...")
            add_column_query = text("""
                ALTER TABLE detergent_orders
                ADD COLUMN customer_email VARCHAR(200)
            """)

            conn.execute(add_column_query)
            conn.commit()

            print("[Migration] ✓ Successfully added customer_email column")
            return True

    except Exception as e:
        print(f"[Migration] ❌ Error: {e}")
        return False
    finally:
        engine.dispose()

if __name__ == "__main__":
    print("=" * 60)
    print("Database Migration: Add customer_email column")
    print("=" * 60)

    success = add_email_column()

    if success:
        print("\n✅ Migration completed successfully!")
    else:
        print("\n❌ Migration failed!")
