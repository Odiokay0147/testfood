"""
migrate_add_vendor_fields.py
Run this ONCE from your project root:

    python migrate_add_vendor_fields.py

It adds the `role` and `vendor_id` columns to the existing users table
without touching any other data.
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "food_app.db")


def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Check existing columns
    cursor.execute("PRAGMA table_info(users);")
    existing_columns = {row[1] for row in cursor.fetchall()}
    print(f"Existing columns: {existing_columns}")

    # Add `role` if missing
    if "role" not in existing_columns:
        cursor.execute("ALTER TABLE users ADD COLUMN role VARCHAR DEFAULT 'customer';")
        print("✅ Added column: role (default='customer')")
    else:
        print("⏭️  Column already exists: role")

    # Add `vendor_id` if missing
    if "vendor_id" not in existing_columns:
        cursor.execute("ALTER TABLE users ADD COLUMN vendor_id INTEGER REFERENCES vendors(id);")
        print("✅ Added column: vendor_id (nullable)")
    else:
        print("⏭️  Column already exists: vendor_id")

    conn.commit()
    conn.close()
    print("\nMigration complete. You can now run uvicorn normally.")


if __name__ == "__main__":
    migrate()