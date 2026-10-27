from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

DB = Path.home() / ".iris-light" / "iris_light.db"


def main() -> int:
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    print("tables", tables)
    for name in tables:
        if "chat" in name.lower() or "conv" in name.lower() or "message" in name.lower():
            n = con.execute(f"SELECT count(*) FROM {name}").fetchone()[0]
            print(name, "count", n)
            cols = [d[0] for d in con.execute(f"PRAGMA table_info({name})").fetchall()]
            print(" cols", cols)
            rows = con.execute(f"SELECT * FROM {name} ORDER BY rowid DESC LIMIT 5").fetchall()
            for row in rows:
                data = {k: row[k] for k in row.keys()}
                for key in ("content", "model_content", "text"):
                    if key in data and isinstance(data[key], str) and len(data[key]) > 160:
                        data[key] = data[key][:160] + "..."
                print(" ", data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
