from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from utils.db_runtime import get_database_mode, get_postgres_connection  # noqa: E402


def main() -> None:
    if get_database_mode() != "postgres":
        print("APP_DATABASE_MODE doit valoir postgres pour appliquer le schéma Supabase.")
        print("Exemple PowerShell :")
        print('$env:APP_DATABASE_MODE="postgres"')
        print('$env:DATABASE_URL="postgresql://..."')
        raise SystemExit(1)

    schema_path = ROOT / "deployment" / "supabase_schema.sql"
    if not schema_path.exists():
        print("Fichier introuvable :", schema_path)
        raise SystemExit(1)

    sql = schema_path.read_text(encoding="utf-8")
    with get_postgres_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
    print("Schéma Supabase/PostgreSQL appliqué avec succès.")


if __name__ == "__main__":
    main()
