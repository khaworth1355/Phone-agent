#!/usr/bin/env python3
"""
Database Migration Script - Add transcription_type column
Run this script to apply the schema changes for transcription type tracking
"""
import sys
import psycopg2
from config import Config


def run_migration():
    """Apply database migration for transcription_type column"""

    print("=" * 60)
    print("Database Migration: Add transcription_type Column")
    print("=" * 60)
    print()

    # Check database URL is configured
    if not Config.DATABASE_URL:
        print("❌ ERROR: DATABASE_URL not configured")
        print("Please set DATABASE_URL in your .env file")
        return False

    print("✓ Database URL configured")
    print()

    try:
        # Connect to database
        print("[1/5] Connecting to PostgreSQL database...")
        conn = psycopg2.connect(Config.DATABASE_URL)
        cursor = conn.cursor()
        print("✓ Connected successfully")
        print()

        # Read migration SQL
        print("[2/5] Reading migration file...")
        with open('migration_add_transcription_type.sql', 'r') as f:
            migration_sql = f.read()
        print("✓ Migration SQL loaded")
        print()

        # Execute migration
        print("[3/5] Executing migration statements...")
        statements = migration_sql.split(';')
        executed = 0

        for statement in statements:
            statement = statement.strip()
            # Skip empty statements and comments
            if statement and not statement.startswith('--'):
                try:
                    cursor.execute(statement)
                    executed += 1
                    # Show what we're doing
                    if 'ALTER TABLE' in statement:
                        print("  ✓ Added column: transcription_type")
                    elif 'UPDATE' in statement:
                        print("  ✓ Updated existing records")
                    elif 'CREATE INDEX' in statement:
                        print("  ✓ Created index: idx_transcripts_type")
                    elif 'COMMENT' in statement:
                        print("  ✓ Added column comment")
                except psycopg2.Error as e:
                    # Check if error is because column already exists
                    if 'already exists' in str(e):
                        print(f"  ⚠️  Already applied: {str(e).split(':')[0]}")
                        conn.rollback()
                        # Continue with next statement
                    else:
                        raise

        conn.commit()
        print(f"✓ Executed {executed} statements")
        print()

        # Verify column exists
        print("[4/5] Verifying migration...")
        cursor.execute("""
            SELECT column_name, data_type, column_default
            FROM information_schema.columns
            WHERE table_name = 'call_transcripts'
              AND column_name = 'transcription_type'
        """)
        result = cursor.fetchone()

        if result:
            print(f"  ✓ Column exists: {result[0]}")
            print(f"    - Type: {result[1]}")
            print(f"    - Default: {result[2]}")
        else:
            print("  ❌ Column not found after migration!")
            cursor.close()
            conn.close()
            return False

        # Verify index exists
        cursor.execute("""
            SELECT indexname
            FROM pg_indexes
            WHERE tablename = 'call_transcripts'
              AND indexname = 'idx_transcripts_type'
        """)
        if cursor.fetchone():
            print("  ✓ Index exists: idx_transcripts_type")
        else:
            print("  ⚠️  Index not found (may already exist)")

        print()

        # Show statistics
        print("[5/5] Migration statistics...")
        cursor.execute("""
            SELECT
                transcription_type,
                COUNT(*) as count
            FROM call_transcripts
            GROUP BY transcription_type
            ORDER BY transcription_type
        """)

        stats = cursor.fetchall()
        if stats:
            print("  Current transcript counts:")
            for row in stats:
                print(f"    - {row[0]}: {row[1]} records")
        else:
            print("  (No transcripts in database yet)")

        print()

        # Cleanup
        cursor.close()
        conn.close()

        print("=" * 60)
        print("🎉 Migration completed successfully!")
        print("=" * 60)
        print()
        print("Next steps:")
        print("1. Restart your application: pm2 restart phone-agent")
        print("2. Make a test call to verify transcription works")
        print("3. Check logs for [Batch Transcription] messages")
        print()

        return True

    except FileNotFoundError:
        print("❌ ERROR: migration_add_transcription_type.sql not found")
        print("Make sure you're running this from the project directory")
        return False

    except psycopg2.Error as e:
        print(f"❌ Database error: {e}")
        if conn:
            conn.rollback()
        return False

    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)
