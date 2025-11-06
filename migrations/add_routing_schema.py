"""
Database migration: Add call routing tables
Run once: python migrations/add_routing_schema.py

This script creates:
- departments table (Sales, Support, Billing)
- routing_rules table (keyword-based routing)
- call_routes table (routing decisions log)
- call_transcripts table (conversation storage)
- calls_metadata table (call summaries)
"""
import os
import sys

# Add parent directory to path so we can import config
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from config import Config


def add_routing_schema():
    """Run the routing schema migration"""

    if not Config.DATABASE_URL:
        print("❌ ERROR: DATABASE_URL not configured in .env file")
        print("Please set DATABASE_URL in your .env file")
        return False

    print("=" * 60)
    print("Call Routing Schema Migration")
    print("=" * 60)
    print(f"Database: {Config.DATABASE_URL.split('@')[-1] if '@' in Config.DATABASE_URL else 'configured'}")
    print()

    try:
        # Create engine
        print("[1/4] Connecting to database...")
        engine = create_engine(Config.DATABASE_URL)

        # Read SQL file
        print("[2/4] Reading migration SQL...")
        sql_file_path = os.path.join(os.path.dirname(__file__), 'routing_schema.sql')

        with open(sql_file_path, 'r', encoding='utf-8') as f:
            sql_content = f.read()

        # Execute migration
        print("[3/4] Executing migration...")
        with engine.connect() as conn:
            # Split by semicolon and execute each statement
            statements = [s.strip() for s in sql_content.split(';') if s.strip()]

            for i, statement in enumerate(statements, 1):
                # Skip comments-only statements
                if statement.startswith('--') or not statement.strip('--').strip():
                    continue

                try:
                    conn.execute(text(statement))
                    conn.commit()
                    print(f"   ✓ Statement {i}/{len(statements)} executed")
                except Exception as e:
                    # If table already exists, that's okay
                    if 'already exists' in str(e).lower():
                        print(f"   ⚠ Statement {i}/{len(statements)} - Table already exists (skipping)")
                    else:
                        raise

        print("[4/4] Verifying tables...")

        # Verify tables were created
        with engine.connect() as conn:
            # Check for each table
            tables_to_check = ['departments', 'routing_rules', 'call_routes', 'call_transcripts', 'calls_metadata']

            for table in tables_to_check:
                result = conn.execute(text(f"""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_name = '{table}'
                    );
                """))
                exists = result.scalar()

                if exists:
                    print(f"   ✓ Table '{table}' exists")
                else:
                    print(f"   ❌ Table '{table}' NOT FOUND")
                    return False

        print()
        print("=" * 60)
        print("✅ Migration completed successfully!")
        print("=" * 60)
        print()
        print("Next steps:")
        print("1. Verify tables in your database")
        print("2. Check seed data: SELECT * FROM departments;")
        print("3. Check routing rules: SELECT * FROM routing_rules;")
        print()

        return True

    except Exception as e:
        print()
        print("=" * 60)
        print("❌ Migration failed!")
        print("=" * 60)
        print(f"Error: {e}")
        print()

        import traceback
        traceback.print_exc()

        return False


if __name__ == "__main__":
    success = add_routing_schema()
    sys.exit(0 if success else 1)
