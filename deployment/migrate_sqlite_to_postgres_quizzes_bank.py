from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from psycopg.types.json import Jsonb  # noqa: E402
from utils.db_runtime import get_database_mode, get_postgres_connection, get_sqlite_path  # noqa: E402


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    return row is not None


def safe_json(value):
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return value


def reset_sequence(cur, table: str) -> None:
    try:
        cur.execute(
            "SELECT setval(pg_get_serial_sequence(%s, 'id'), COALESCE((SELECT MAX(id) FROM " + table + "), 1), true)",
            (table,),
        )
    except Exception:
        pass


def main() -> None:
    if get_database_mode() != "postgres":
        print("APP_DATABASE_MODE doit valoir postgres.")
        raise SystemExit(1)

    sqlite_path = get_sqlite_path()
    if not sqlite_path.exists():
        print("Base SQLite introuvable :", sqlite_path)
        raise SystemExit(1)

    sqlite_conn = sqlite3.connect(sqlite_path)
    sqlite_conn.row_factory = sqlite3.Row
    copied = {}

    with get_postgres_connection() as pg_conn:
        with pg_conn.cursor() as cur:
            if table_exists(sqlite_conn, "saved_quizzes"):
                rows = sqlite_conn.execute("SELECT * FROM saved_quizzes").fetchall()
                for row in rows:
                    cur.execute("""
                        INSERT INTO saved_quizzes (
                            id, title, module, difficulty, question_count,
                            quiz_json, source_preview, created_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id)
                        DO UPDATE SET
                            title = EXCLUDED.title,
                            module = EXCLUDED.module,
                            difficulty = EXCLUDED.difficulty,
                            question_count = EXCLUDED.question_count,
                            quiz_json = EXCLUDED.quiz_json,
                            source_preview = EXCLUDED.source_preview
                    """, (
                        row["id"],
                        row["title"],
                        row["module"],
                        row["difficulty"],
                        row["question_count"],
                        Jsonb(safe_json(row["quiz_json"])),
                        row["source_preview"],
                        row["created_at"],
                    ))
                copied["saved_quizzes"] = len(rows)

            if table_exists(sqlite_conn, "question_bank"):
                rows = sqlite_conn.execute("SELECT * FROM question_bank").fetchall()
                for row in rows:
                    cur.execute("""
                        INSERT INTO question_bank (
                            id, question_hash, source_quiz_id, source_quiz_title,
                            question_type, domain, subdomain, difficulty,
                            cognitive_level, competency, concept_evaluated,
                            question_text, question_json, is_active, created_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (question_hash)
                        DO UPDATE SET
                            source_quiz_id = EXCLUDED.source_quiz_id,
                            source_quiz_title = EXCLUDED.source_quiz_title,
                            question_type = EXCLUDED.question_type,
                            domain = EXCLUDED.domain,
                            subdomain = EXCLUDED.subdomain,
                            difficulty = EXCLUDED.difficulty,
                            cognitive_level = EXCLUDED.cognitive_level,
                            competency = EXCLUDED.competency,
                            concept_evaluated = EXCLUDED.concept_evaluated,
                            question_text = EXCLUDED.question_text,
                            question_json = EXCLUDED.question_json,
                            is_active = EXCLUDED.is_active
                    """, (
                        row["id"],
                        row["question_hash"],
                        row["source_quiz_id"],
                        row["source_quiz_title"],
                        row["question_type"],
                        row["domain"],
                        row["subdomain"],
                        row["difficulty"],
                        row["cognitive_level"],
                        row["competency"],
                        row["concept_evaluated"],
                        row["question_text"],
                        Jsonb(safe_json(row["question_json"])),
                        bool(row["is_active"]),
                        row["created_at"],
                    ))
                copied["question_bank"] = len(rows)

            reset_sequence(cur, "saved_quizzes")
            reset_sequence(cur, "question_bank")

        pg_conn.commit()

    sqlite_conn.close()

    print("Migration SQLite -> Supabase terminée.")
    for table, count in copied.items():
        print(f"- {table}: {count} ligne(s) traitée(s)")


if __name__ == "__main__":
    main()
