"""
Database Migration: Drop detergent_orders table
"""
from sqlalchemy import create_engine, text, inspect
from config import Config
from datetime import datetime

def verify_no_foreign_keys():
    """Verify no tables reference detergent_orders"""
    engine = create_engine(Config.DATABASE_URL)
    inspector = inspect(engine)

    for table_name in inspector.get_table_names():
        for fk in inspector.get_foreign_keys(table_name):
            if fk['referred_table'] == 'detergent_orders':
                raise Exception(f"ERROR: {table_name} has FK to detergent_orders")

    print("No foreign key dependencies")
    return True

def backup_schema():
    """Backup table schema"""
    engine = create_engine(Config.DATABASE_URL)

    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT column_name, data_type, character_maximum_length, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'detergent_orders'
            ORDER BY ordinal_position
        """))

        schema = list(result)
        if schema:
            filename = f'detergent_orders_schema_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt'
            with open(filename, 'w') as f:
                f.write("-- Schema Backup\n")
                for col in schema:
                    f.write(f"{col}\n")
            print(f"Schema backed up: {filename}")
        else:
            print("Warning: No schema found for detergent_orders table")

    return True

def drop_table():
    """Drop detergent_orders table"""
    engine = create_engine(Config.DATABASE_URL)

    with engine.connect() as conn:
        # Check if exists
        result = conn.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'detergent_orders'
            )
        """))

        if not result.scalar():
            print("Warning: Table 'detergent_orders' does not exist")
            return True

        # Drop table
        print("Dropping table 'detergent_orders'...")
        conn.execute(text("DROP TABLE IF EXISTS detergent_orders CASCADE"))
        conn.commit()

        print("Table dropped successfully")
        return True

if __name__ == "__main__":
    print("="*60)
    print("DATABASE MIGRATION: Drop detergent_orders table")
    print("="*60)

    verify_no_foreign_keys()
    backup_schema()
    drop_table()

    print("="*60)
    print("MIGRATION COMPLETE")
    print("="*60)
