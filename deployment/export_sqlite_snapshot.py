from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from utils.db_runtime import get_sqlite_path  # noqa: E402


def json_safe(value):
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def main() -> None:
    sqlite_path = get_sqlite_path()
    if not sqlite_path.exists():
        print(f"Base SQLite introuvable : {sqlite_path}")
        raise SystemExit(1)

    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    tables = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type='table'
          AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    ).fetchall()

    snapshot = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "sqlite_path": str(sqlite_path),
        "tables": {},
    }

    for table in tables:
        table_name = table["name"]
        rows = conn.execute(f'SELECT * FROM "{table_name}"').fetchall()
        snapshot["tables"][table_name] = [
            {key: json_safe(row[key]) for key in row.keys()}
            for row in rows
        ]

    conn.close()
    out_dir = ROOT / "deployment" / "snapshots"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"sqlite_snapshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Snapshot SQLite exporté :")
    print(out_path)


if __name__ == "__main__":
    main()
