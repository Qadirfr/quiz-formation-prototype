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


def _json_value(value: Any) -> Any:
    if _pg():
        from psycopg.types.json import Jsonb
        return Jsonb(value)
    return json.dumps(value, ensure_ascii=False)


def _json_display(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _fetchall(sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        if _pg():
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return [_row(r) for r in cur.fetchall()]
        rows = conn.execute(sql, params).fetchall()
        return [_row(r) for r in rows]


def init_learner_db() -> None:
    if _pg():
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS learners (
                        id bigserial PRIMARY KEY,
                        name text NOT NULL,
                        email text NOT NULL UNIQUE,
                        group_name text,
                        created_at timestamptz NOT NULL DEFAULT now()
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS quiz_attempts (
                        id bigserial PRIMARY KEY,
                        learner_id bigint NOT NULL REFERENCES learners(id) ON DELETE CASCADE,
                        quiz_id bigint,
                        quiz_title text NOT NULL,
                        started_at timestamptz NOT NULL DEFAULT now(),
                        finished_at timestamptz,
                        score numeric NOT NULL DEFAULT 0,
                        max_score numeric NOT NULL DEFAULT 0,
                        percentage numeric NOT NULL DEFAULT 0,
                        recommended_level text,
                        manual_count integer NOT NULL DEFAULT 0
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS learner_answers (
                        id bigserial PRIMARY KEY,
                        attempt_id bigint NOT NULL REFERENCES quiz_attempts(id) ON DELETE CASCADE,
                        question_index integer NOT NULL,
                        question_type text,
                        question_text text,
                        user_answer_json jsonb,
                        correct_answer_json jsonb,
                        is_correct boolean,
                        score numeric NOT NULL DEFAULT 0,
                        domain text,
                        subdomain text,
                        learning_objective text,
                        concept_evaluated text,
                        cognitive_level text,
                        competency text,
                        explanation text,
                        selected_feedback text,
                        correct_feedback text,
                        remediation text,
                        created_at timestamptz NOT NULL DEFAULT now()
                    )
                """)
            conn.commit()
        return

    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS learners (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                group_name TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS quiz_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                learner_id INTEGER NOT NULL,
                quiz_id INTEGER,
                quiz_title TEXT NOT NULL,
                started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                finished_at TEXT,
                score REAL NOT NULL DEFAULT 0,
                max_score REAL NOT NULL DEFAULT 0,
                percentage REAL NOT NULL DEFAULT 0,
                recommended_level TEXT,
                manual_count INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (learner_id) REFERENCES learners(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS learner_answers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                attempt_id INTEGER NOT NULL,
                question_index INTEGER NOT NULL,
                question_type TEXT,
                question_text TEXT,
                user_answer_json TEXT,
                correct_answer_json TEXT,
                is_correct INTEGER,
                score REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (attempt_id) REFERENCES quiz_attempts(id)
            )
        """)
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(learner_answers)").fetchall()}
        extras = {
            "domain": "TEXT",
            "subdomain": "TEXT",
            "learning_objective": "TEXT",
            "concept_evaluated": "TEXT",
            "cognitive_level": "TEXT",
            "competency": "TEXT",
            "explanation": "TEXT",
            "selected_feedback": "TEXT",
            "correct_feedback": "TEXT",
            "remediation": "TEXT",
        }
        for name, typ in extras.items():
            if name not in cols:
                conn.execute(f"ALTER TABLE learner_answers ADD COLUMN {name} {typ}")
        conn.commit()


def create_or_get_learner(name: str, email: str, group_name: str = "") -> Dict[str, Any]:
    init_learner_db()
    clean_email = email.strip().lower()
    clean_name = name.strip()
    clean_group = group_name.strip()

    if _pg():
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO learners (name, email, group_name)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (email)
                    DO UPDATE SET name = EXCLUDED.name, group_name = EXCLUDED.group_name
                    RETURNING id, name, email, group_name, created_at
                """, (clean_name, clean_email, clean_group))
                row = cur.fetchone()
            conn.commit()
        return _row(row)

    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, name, email, group_name, created_at FROM learners WHERE email = ?",
            (clean_email,),
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE learners SET name = ?, group_name = ? WHERE id = ?",
                (clean_name, clean_group, row["id"]),
            )
            conn.commit()
            row = conn.execute(
                "SELECT id, name, email, group_name, created_at FROM learners WHERE id = ?",
                (row["id"],),
            ).fetchone()
            return dict(row)

        cursor = conn.execute(
            "INSERT INTO learners (name, email, group_name) VALUES (?, ?, ?)",
            (clean_name, clean_email, clean_group),
        )
        conn.commit()
        row = conn.execute(
            "SELECT id, name, email, group_name, created_at FROM learners WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
        return dict(row)


def start_attempt(learner_id: int, quiz_id: Optional[int], quiz_title: str) -> int:
    init_learner_db()
    if _pg():
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO quiz_attempts (learner_id, quiz_id, quiz_title)
                    VALUES (%s, %s, %s)
                    RETURNING id
                """, (learner_id, quiz_id, quiz_title))
                row = cur.fetchone()
            conn.commit()
        return int(row["id"])

    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO quiz_attempts (learner_id, quiz_id, quiz_title) VALUES (?, ?, ?)",
            (learner_id, quiz_id, quiz_title),
        )
        conn.commit()
        return int(cursor.lastrowid)


def save_attempt_result(
    attempt_id: int,
    question_index: int,
    question: Dict[str, Any],
    user_answer: Any,
    correct_answer: Any,
    is_correct: Optional[bool],
    score: float,
    selected_feedback: str = "",
    correct_feedback: str = "",
) -> None:
    init_learner_db()
    is_correct_db = None if is_correct is None else (bool(is_correct) if _pg() else (1 if is_correct else 0))
    values = (
        attempt_id,
        question_index,
        question.get("type", ""),
        question.get("question", ""),
        _json_value(user_answer),
        _json_value(correct_answer),
        is_correct_db,
        float(score),
        question.get("domain", "") or question.get("domaine", ""),
        question.get("subdomain", "") or question.get("sous_domaine", ""),
        question.get("learning_objective", "") or question.get("objectif_pedagogique", ""),
        question.get("concept_evaluated", ""),
        question.get("cognitive_level", "") or question.get("niveau_cognitif", ""),
        question.get("competency", "") or question.get("competence", ""),
        question.get("explanation", ""),
        selected_feedback,
        correct_feedback,
        question.get("remediation", "") or question.get("piste_de_revision", ""),
    )

    if _pg():
        sql = """
            INSERT INTO learner_answers (
                attempt_id, question_index, question_type, question_text,
                user_answer_json, correct_answer_json, is_correct, score,
                domain, subdomain, learning_objective, concept_evaluated,
                cognitive_level, competency, explanation, selected_feedback,
                correct_feedback, remediation
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, values)
            conn.commit()
        return

    sql = """
        INSERT INTO learner_answers (
            attempt_id, question_index, question_type, question_text,
            user_answer_json, correct_answer_json, is_correct, score,
            domain, subdomain, learning_objective, concept_evaluated,
            cognitive_level, competency, explanation, selected_feedback,
            correct_feedback, remediation
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    with get_connection() as conn:
        conn.execute(sql, values)
        conn.commit()


def finish_attempt(
    attempt_id: int,
    score: float,
    max_score: float,
    percentage: float,
    recommended_level: str,
    manual_count: int = 0,
) -> None:
    init_learner_db()
    if _pg():
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE quiz_attempts
                    SET finished_at = now(),
                        score = %s,
                        max_score = %s,
                        percentage = %s,
                        recommended_level = %s,
                        manual_count = %s
                    WHERE id = %s
                """, (score, max_score, percentage, recommended_level, manual_count, attempt_id))
            conn.commit()
        return

    with get_connection() as conn:
        conn.execute("""
            UPDATE quiz_attempts
            SET finished_at = CURRENT_TIMESTAMP,
                score = ?,
                max_score = ?,
                percentage = ?,
                recommended_level = ?,
                manual_count = ?
            WHERE id = ?
        """, (score, max_score, percentage, recommended_level, manual_count, attempt_id))
        conn.commit()


def _attempts(where_sql: str = "", params: tuple = (), limit: int = 200) -> List[Dict[str, Any]]:
    if _pg():
        sql = f"""
            SELECT
                qa.id, qa.quiz_id, qa.quiz_title, qa.started_at, qa.finished_at,
                qa.score::float AS score,
                qa.max_score::float AS max_score,
                qa.percentage::float AS percentage,
                qa.recommended_level, qa.manual_count,
                qa.started_at AS created_at,
                l.name AS learner_name, l.email AS learner_email, l.group_name
            FROM quiz_attempts qa
            JOIN learners l ON l.id = qa.learner_id
            {where_sql}
            ORDER BY qa.started_at DESC, qa.id DESC
            LIMIT %s
        """
        return _fetchall(sql, (*params, limit))

    sql = f"""
        SELECT
            qa.id, qa.quiz_id, qa.quiz_title, qa.started_at, qa.finished_at,
            qa.score, qa.max_score, qa.percentage,
            qa.recommended_level, qa.manual_count,
            qa.started_at AS created_at,
            l.name AS learner_name, l.email AS learner_email, l.group_name
        FROM quiz_attempts qa
        JOIN learners l ON l.id = qa.learner_id
        {where_sql}
        ORDER BY datetime(qa.started_at) DESC, qa.id DESC
        LIMIT ?
    """
    return _fetchall(sql, (*params, limit))


def get_attempts_summary(limit: int = 200) -> List[Dict[str, Any]]:
    init_learner_db()
    return _attempts(limit=limit)


def get_attempts_for_learner_email(email: str, limit: int = 100) -> List[Dict[str, Any]]:
    init_learner_db()
    clean_email = email.strip().lower()
    where = "WHERE lower(l.email) = %s" if _pg() else "WHERE lower(l.email) = ?"
    return _attempts(where, (clean_email,), limit)


def get_attempt_answers(attempt_id: int) -> List[Dict[str, Any]]:
    init_learner_db()
    if _pg():
        sql = """
            SELECT
                id, question_index, question_type, question_text,
                user_answer_json, correct_answer_json, is_correct,
                score::float AS score,
                domain, subdomain, learning_objective, concept_evaluated,
                cognitive_level, competency, explanation,
                selected_feedback, correct_feedback, remediation, created_at
            FROM learner_answers
            WHERE attempt_id = %s
            ORDER BY question_index ASC
        """
        rows = _fetchall(sql, (attempt_id,))
    else:
        sql = """
            SELECT
                id, question_index, question_type, question_text,
                user_answer_json, correct_answer_json, is_correct,
                score,
                domain, subdomain, learning_objective, concept_evaluated,
                cognitive_level, competency, explanation,
                selected_feedback, correct_feedback, remediation, created_at
            FROM learner_answers
            WHERE attempt_id = ?
            ORDER BY question_index ASC
        """
        rows = _fetchall(sql, (attempt_id,))

    for item in rows:
        if item.get("is_correct") is not None:
            item["is_correct"] = bool(item["is_correct"])
        item["user_answer_json"] = _json_display(item.get("user_answer_json"))
        item["correct_answer_json"] = _json_display(item.get("correct_answer_json"))
    return rows
