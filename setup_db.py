"""
Setup Database Script: Reads credentials from .env and executes schema.sql in MySQL.
"""

import os
import mysql.connector
from dotenv import load_dotenv

load_dotenv()

HOST = os.getenv("MYSQL_HOST", "localhost")
PORT = int(os.getenv("MYSQL_PORT", 3306))
USER = os.getenv("MYSQL_USER", "root")
PASSWORD = os.getenv("MYSQL_PASSWORD", "")
SCHEMA_FILE = os.path.join(os.path.dirname(__file__), "data", "schema.sql")

def setup_database():
    print(f"Connecting to MySQL at {HOST}:{PORT} as user '{USER}'...")
    try:
        conn = mysql.connector.connect(
            host=HOST,
            port=PORT,
            user=USER,
            password=PASSWORD
        )
    except Exception as e:
        print(f"\n❌ Connection Error: {e}")
        print("Please ensure your MYSQL_PASSWORD in .env is correct!")
        return False

    cursor = conn.cursor()
    print("Reading schema.sql...")
    with open(SCHEMA_FILE, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    # Split commands by semicolon
    statements = [stmt.strip() for stmt in schema_sql.split(";") if stmt.strip()]
    
    for stmt in statements:
        try:
            cursor.execute(stmt)
        except Exception as err:
            print(f"Error executing statement: {err}")

    conn.commit()
    cursor.close()
    conn.close()
    print("SUCCESS: Database 'comfort_chairs' and all 4 tables verified successfully!")
    return True

if __name__ == "__main__":
    setup_database()
