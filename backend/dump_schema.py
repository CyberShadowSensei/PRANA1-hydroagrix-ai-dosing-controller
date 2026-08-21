import sqlite3
import os

db_paths = [
    "E:\\Hydroagrix Ai\\Ai Dosing Unit\\mydatabase.db",
    "E:\\Hydroagrix Ai\\Ai Dosing Unit\\backend\\mydatabase.db",
    "E:\\Hydroagrix Ai\\Ai Dosing Unit\\backend\\instance\\mydatabase.db"
]

for db_path in db_paths:
    print("\n========================================")
    print("Checking database:", db_path)
    if not os.path.exists(db_path):
        print("File does not exist!")
        continue
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        print("Tables:", tables)
        
        for table_tuple in tables:
            table = table_tuple[0]
            cursor.execute(f"SELECT COUNT(*) FROM {table};")
            count = cursor.fetchone()[0]
            print(f"  Table '{table}' row count: {count}")
    except Exception as e:
        print("Error:", e)
    conn.close()
