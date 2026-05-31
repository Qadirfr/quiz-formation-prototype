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
    return conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None


def safe_json(value):
    if value is None:
        return None
    try:
        return json.loads(value)
    except Exception:
        return value


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
            if table_exists(sqlite_conn, "learners"):
                rows = sqlite_conn.execute("SELECT * FROM learners").fetchall()
                for row in rows:
                    cur.execute("""
                        INSERT INTO learners (id, name, email, group_name, created_at)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (email)
                        DO UPDATE SET name = EXCLUDED.name, group_name = EXCLUDED.group_name
                    """, (row["id"], row["name"], row["email"], row["group_name"], row["created_at"]))
                copied["learners"] = len(rows)

            if table_exists(sqlite_conn, "training_sessions"):
                rows = sqlite_conn.execute("SELECT * FROM training_sessions").fetchall()
                for row in rows:
                    cur.execute("""
                        INSERT INTO training_sessions (
                            id, title, access_code, mode, source, status,
                            current_question_index, show_correction, questions_json,
                            created_at, closed_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (access_code) DO NOTHING
                    """, (
                        row["id"], row["title"], row["access_code"], row["mode"], row["source"], row["status"],
                        row["current_question_index"], bool(row["show_correction"]), Jsonb(safe_json(row["questions_json"])),
                        row["created_at"], row["closed_at"],
                    ))
                copied["training_sessions"] = len(rows)

            if table_exists(sqlite_conn, "session_participants"):
                rows = sqlite_conn.execute("SELECT * FROM session_participants").fetchall()
                for row in rows:
                    cur.execute("""
                        INSERT INTO session_participants (id, session_id, learner_id, joined_at)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (session_id, learner_id) DO NOTHING
                    """, (row["id"], row["session_id"], row["learner_id"], row["joined_at"]))
                copied["session_participants"] = len(rows)

            if table_exists(sqlite_conn, "session_answers"):
                rows = sqlite_conn.execute("SELECT * FROM session_answers").fetchall()
                for row in rows:
                    cur.execute("""
                        INSERT INTO session_answers (
                            id, session_id, participant_id, learner_id, question_index,
                            question_type, question_text, user_answer_json, correct_answer_json,
                            is_correct, score, selected_feedback, correct_feedback, answered_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (session_id, participant_id, question_index) DO NOTHING
                    """, (
                        row["id"], row["session_id"], row["participant_id"], row["learner_id"], row["question_index"],
                        row["question_type"], row["question_text"], Jsonb(safe_json(row["user_answer_json"])),
                        Jsonb(safe_json(row["correct_answer_json"])),
                        None if row["is_correct"] is None else bool(row["is_correct"]),
                        row["score"], row["selected_feedback"], row["correct_feedback"], row["answered_at"],
                    ))
                copied["session_answers"] = len(rows)

            for table in ["learners", "training_sessions", "session_participants", "session_answers"]:
                try:
                    cur.execute("SELECT setval(pg_get_serial_sequence(%s, 'id'), COALESCE((SELECT MAX(id) FROM " + table + "), 1), true)", (table,))
                except Exception:
                    pass

        pg_conn.commit()

    sqlite_conn.close()
    print("Migration SQLite -> Supabase terminée.")
    for table, count in copied.items():
        print(f"- {table}: {count} ligne(s) traitée(s)")


if __name__ == "__main__":
    main()
