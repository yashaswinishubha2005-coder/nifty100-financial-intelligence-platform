import sqlite3
from pathlib import Path

db_path = Path("data") / "nifty100.db"
sql_path = Path("notebooks") / "exploratory_queries.sql"

conn = sqlite3.connect(db_path)

with open(sql_path, "r", encoding="utf-8") as f:
    sql = f.read()

conn.executescript(sql)

conn.close()

print("All SQL queries executed successfully!")