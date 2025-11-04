"""
Database Migration Script
Updates detergent_orders table schema to fix issues from previous version
"""
from config import Config
import psycopg2

def migrate_database():
    """Update database schema to fix state and add quantity fields"""

    print("[Migration] Connecting to database...")
    conn = psycopg2.connect(Config.DATABASE_URL)
    cursor = conn.cursor()

    try:
        print("[Migration] Checking table structure...")

        # Step 1: Update address_state from varchar(2) to varchar(50)
        print("[Migration] Updating address_state column to varchar(50)...")
        cursor.execute("""
            ALTER TABLE detergent_orders
            ALTER COLUMN address_state TYPE varchar(50);
        """)
        print("[Migration] ✓ address_state updated")

        # Step 2: Check if quantity column exists
        cursor.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name='detergent_orders' AND column_name='quantity';
        """)

        if not cursor.fetchone():
            # Add quantity column
            print("[Migration] Adding quantity column...")
            cursor.execute("""
                ALTER TABLE detergent_orders
                ADD COLUMN quantity INTEGER NOT NULL DEFAULT 1;
            """)
            print("[Migration] ✓ quantity column added")
        else:
            print("[Migration] ✓ quantity column already exists")

        # Commit changes
        conn.commit()
        print("[Migration] ✓ Database migration completed successfully!")

    except Exception as e:
        conn.rollback()
        print(f"[Migration] ❌ Error: {e}")
        raise

    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    print("="*80)
    print("DATABASE MIGRATION - Detergent Orders Schema Update")
    print("="*80)
    print("This will update the detergent_orders table to:")
    print("  1. Change address_state from varchar(2) to varchar(50)")
    print("  2. Add quantity column (if missing)")
    print("="*80)

    response = input("\nProceed with migration? (yes/no): ")

    if response.lower() in ['yes', 'y']:
        migrate_database()
    else:
        print("[Migration] Cancelled by user")
