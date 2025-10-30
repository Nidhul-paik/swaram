# dump_sqlite_data.py
import sqlite3
import json

conn = sqlite3.connect("sql.db")
conn.row_factory = sqlite3.Row
cur = conn.cursor()

data = {}

for table in ["users", "audio_files", "image_contributions"]:
    try:
        cur.execute(f"SELECT * FROM {table}")
        rows = [dict(row) for row in cur.fetchall()]
        data[table] = rows
    except Exception as e:
        print(f"Error reading {table}: {e}")

with open("sqlite_data.json", "w", encoding="utf-8") as f:
    json.dump(data, f, indent=4, ensure_ascii=False)

conn.close()
print("✅ Exported old data to sqlite_data.json")
