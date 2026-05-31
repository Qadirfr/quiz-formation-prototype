from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from utils.db_runtime import get_connection, get_database_mode


def _pg() -> bool:
    return get_database_mode() == "postgres"


def _row(row: Any) -> Dict[str, Any]:
    if row is None:
        return {}
    if isinstance(row, dict):
        return dict(row)
    return dict(row)


def _json_db(value: Any) -> Any:
    if _pg():
        from psycopg.types.json import Jsonb
        return Jsonb(value)
    return json.dumps(value, ensure_ascii=False)


def _json_load(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return value


def _fetchall(sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        if _pg():
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return [_row(r) for r in cur.fetchall()]
        rows = conn.execute(sql, params).fetchall()
        return [_row(r) for r in rows]


def init_db() -> None:
    init_quiz_db()


def init_quiz_db() -> None:
    init_quiz_history_db()


def init_quiz_history_db() -> None:
    if _pg():
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS saved_quizzes (
                        id bigserial PRIMARY KEY,
                        title text NOT NULL,
                        module text,
                        difficulty text,
                        question_count integer NOT NULL DEFAULT 0,
                        quiz_json jsonb NOT NULL,
                        source_preview text,
                        created_at timestamptz NOT NULL DEFAULT now()
                    )
                """)
            conn.commit()
        return

    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS saved_quizzes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                module TEXT,
                difficulty TEXT,
                question_count INTEGER NOT NULL DEFAULT 0,
                quiz_json TEXT NOT NULL,
                source_preview TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()


def save_quiz(
    quiz: Dict[str, Any],
    title: str = "",
    module: str = "",
    difficulty: str = "",
    source_preview: str = "",
) -> int:
    init_quiz_history_db()
    quiz_title = title or quiz.get("quiz_title", "") or "Quiz sans titre"
    question_count = len(quiz.get("questions", []) or [])

    if _pg():
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO saved_quizzes (
                        title, module, difficulty, question_count, quiz_json, source_preview
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    quiz_title,
                    module,
                    difficulty,
                    question_count,
                    _json_db(quiz),
                    source_preview,
                ))
                row = cur.fetchone()
            conn.commit()
        return int(row["id"])

    with get_connection() as conn:
        cursor = conn.execute("""
            INSERT INTO saved_quizzes (
                title, module, difficulty, question_count, quiz_json, source_preview
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            quiz_title,
            module,
            difficulty,
            question_count,
            json.dumps(quiz, ensure_ascii=False),
            source_preview,
        ))
        conn.commit()
        return int(cursor.lastrowid)


def list_saved_quizzes(limit: int = 200) -> List[Dict[str, Any]]:
    init_quiz_history_db()
    if _pg():
        sql = """
            SELECT
                id, title, module, difficulty, question_count,
                source_preview, created_at
            FROM saved_quizzes
            ORDER BY created_at DESC, id DESC
            LIMIT %s
        """
        return _fetchall(sql, (limit,))

    sql = """
        SELECT
            id, title, module, difficulty, question_count,
            source_preview, created_at
        FROM saved_quizzes
        ORDER BY datetime(created_at) DESC, id DESC
        LIMIT ?
    """
    return _fetchall(sql, (limit,))


def load_quiz(quiz_id: int) -> Optional[Dict[str, Any]]:
    init_quiz_history_db()
    if _pg():
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT quiz_json FROM saved_quizzes WHERE id = %s", (quiz_id,))
                row = cur.fetchone()
        if not row:
            return None
        return _json_load(row["quiz_json"])

    with get_connection() as conn:
        row = conn.execute("SELECT quiz_json FROM saved_quizzes WHERE id = ?", (quiz_id,)).fetchone()
    if not row:
        return None
    return _json_load(row["quiz_json"])


def get_saved_quiz(quiz_id: int) -> Optional[Dict[str, Any]]:
    return load_quiz(quiz_id)


def delete_quiz(quiz_id: int) -> None:
    init_quiz_history_db()
    if _pg():
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM saved_quizzes WHERE id = %s", (quiz_id,))
            conn.commit()
        return

    with get_connection() as conn:
        conn.execute("DELETE FROM saved_quizzes WHERE id = ?", (quiz_id,))
        conn.commit()


def delete_saved_quiz(quiz_id: int) -> None:
    delete_quiz(quiz_id)


def export_quiz_json(quiz_id: int) -> str:
    quiz = load_quiz(quiz_id)
    return json.dumps(quiz or {}, ensure_ascii=False, indent=2)


def update_saved_quiz(
    quiz_id: int,
    quiz: Dict[str, Any],
    title: Optional[str] = None,
    module: Optional[str] = None,
    difficulty: Optional[str] = None,
    source_preview: Optional[str] = None,
) -> None:
    init_quiz_history_db()
    current_title = title or quiz.get("quiz_title", "") or "Quiz sans titre"
    question_count = len(quiz.get("questions", []) or [])

    if _pg():
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE saved_quizzes
                    SET title = %s,
                        module = COALESCE(%s, module),
                        difficulty = COALESCE(%s, difficulty),
                        question_count = %s,
                        quiz_json = %s,
                        source_preview = COALESCE(%s, source_preview)
                    WHERE id = %s
                """, (
                    current_title,
                    module,
                    difficulty,
                    question_count,
                    _json_db(quiz),
                    source_preview,
                    quiz_id,
                ))
            conn.commit()
        return

    with get_connection() as conn:
        conn.execute("""
            UPDATE saved_quizzes
            SET title = ?,
                module = COALESCE(?, module),
                difficulty = COALESCE(?, difficulty),
                question_count = ?,
                quiz_json = ?,
                source_preview = COALESCE(?, source_preview)
            WHERE id = ?
        """, (
            current_title,
            module,
            difficulty,
            question_count,
            json.dumps(quiz, ensure_ascii=False),
            source_preview,
            quiz_id,
        ))
        conn.commit()
