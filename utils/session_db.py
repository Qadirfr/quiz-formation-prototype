from __future__ import annotations

import json
import random
import string
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


def init_session_db() -> None:
    if _pg():
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS training_sessions (
                        id bigserial PRIMARY KEY,
                        title text NOT NULL,
                        access_code text NOT NULL UNIQUE,
                        mode text NOT NULL DEFAULT 'directed',
                        source text,
                        status text NOT NULL DEFAULT 'waiting',
                        current_question_index integer NOT NULL DEFAULT 0,
                        show_correction boolean NOT NULL DEFAULT false,
                        questions_json jsonb NOT NULL,
                        created_at timestamptz NOT NULL DEFAULT now(),
                        closed_at timestamptz
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS session_participants (
                        id bigserial PRIMARY KEY,
                        session_id bigint NOT NULL REFERENCES training_sessions(id) ON DELETE CASCADE,
                        learner_id bigint NOT NULL REFERENCES learners(id) ON DELETE CASCADE,
                        joined_at timestamptz NOT NULL DEFAULT now(),
                        UNIQUE(session_id, learner_id)
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS session_answers (
                        id bigserial PRIMARY KEY,
                        session_id bigint NOT NULL REFERENCES training_sessions(id) ON DELETE CASCADE,
                        participant_id bigint NOT NULL REFERENCES session_participants(id) ON DELETE CASCADE,
                        learner_id bigint NOT NULL REFERENCES learners(id) ON DELETE CASCADE,
                        question_index integer NOT NULL,
                        question_type text,
                        question_text text,
                        user_answer_json jsonb,
                        correct_answer_json jsonb,
                        is_correct boolean,
                        score numeric NOT NULL DEFAULT 0,
                        selected_feedback text,
                        correct_feedback text,
                        answered_at timestamptz NOT NULL DEFAULT now(),
                        UNIQUE(session_id, participant_id, question_index)
                    )
                """)
            conn.commit()
        return

    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS training_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                access_code TEXT NOT NULL UNIQUE,
                mode TEXT NOT NULL DEFAULT 'directed',
                source TEXT,
                status TEXT NOT NULL DEFAULT 'waiting',
                current_question_index INTEGER NOT NULL DEFAULT 0,
                show_correction INTEGER NOT NULL DEFAULT 0,
                questions_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                closed_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS session_participants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                learner_id INTEGER NOT NULL,
                joined_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(session_id, learner_id),
                FOREIGN KEY (session_id) REFERENCES training_sessions(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS session_answers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                participant_id INTEGER NOT NULL,
                learner_id INTEGER NOT NULL,
                question_index INTEGER NOT NULL,
                question_type TEXT,
                question_text TEXT,
                user_answer_json TEXT,
                correct_answer_json TEXT,
                is_correct INTEGER,
                score REAL NOT NULL DEFAULT 0,
                selected_feedback TEXT,
                correct_feedback TEXT,
                answered_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(session_id, participant_id, question_index),
                FOREIGN KEY (session_id) REFERENCES training_sessions(id),
                FOREIGN KEY (participant_id) REFERENCES session_participants(id)
            )
        """)
        conn.commit()


def generate_session_code(prefix: str = "S") -> str:
    suffix = "".join(random.choice(string.ascii_uppercase + string.digits) for _ in range(6))
    return f"{prefix}-{suffix}"


def create_training_session(title: str, access_code: str, questions: List[Dict[str, Any]], mode: str = "directed", source: str = "") -> int:
    init_session_db()
    clean_code = access_code.strip().upper() or generate_session_code("SESSION")
    if _pg():
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO training_sessions (title, access_code, mode, source, status, current_question_index, show_correction, questions_json)
                    VALUES (%s, %s, %s, %s, 'waiting', 0, false, %s)
                    RETURNING id
                """, (title.strip() or "Session sans titre", clean_code, mode, source, _json_value(questions)))
                row = cur.fetchone()
            conn.commit()
        return int(row["id"])
    with get_connection() as conn:
        cursor = conn.execute("""
            INSERT INTO training_sessions (title, access_code, mode, source, status, current_question_index, show_correction, questions_json)
            VALUES (?, ?, ?, ?, 'waiting', 0, 0, ?)
        """, (title.strip() or "Session sans titre", clean_code, mode, source, _json_value(questions)))
        conn.commit()
        return int(cursor.lastrowid)


def list_training_sessions(limit: int = 100) -> List[Dict[str, Any]]:
    init_session_db()
    if _pg():
        rows = _fetchall("""
            SELECT id, title, access_code, mode, source, status, current_question_index, show_correction, created_at, closed_at
            FROM training_sessions
            ORDER BY created_at DESC, id DESC
            LIMIT %s
        """, (limit,))
    else:
        rows = _fetchall("""
            SELECT id, title, access_code, mode, source, status, current_question_index, show_correction, created_at, closed_at
            FROM training_sessions
            ORDER BY datetime(created_at) DESC, id DESC
            LIMIT ?
        """, (limit,))
    for r in rows:
        r["show_correction"] = bool(r.get("show_correction"))
    return rows


def _session_from_row(row: Any) -> Dict[str, Any]:
    data = _row(row)
    data["show_correction"] = bool(data.get("show_correction"))
    raw = data.get("questions_json") or []
    if isinstance(raw, str):
        try:
            data["questions"] = json.loads(raw)
        except Exception:
            data["questions"] = []
    else:
        data["questions"] = raw
    data.pop("questions_json", None)
    return data


def get_training_session(session_id: int) -> Optional[Dict[str, Any]]:
    init_session_db()
    if _pg():
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM training_sessions WHERE id = %s", (session_id,))
                row = cur.fetchone()
        return _session_from_row(row) if row else None
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM training_sessions WHERE id = ?", (session_id,)).fetchone()
    return _session_from_row(row) if row else None


def get_training_session_by_code(access_code: str) -> Optional[Dict[str, Any]]:
    init_session_db()
    clean_code = access_code.strip().upper()
    if _pg():
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM training_sessions WHERE upper(access_code) = %s", (clean_code,))
                row = cur.fetchone()
        return _session_from_row(row) if row else None
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM training_sessions WHERE upper(access_code) = ?", (clean_code,)).fetchone()
    return _session_from_row(row) if row else None


def update_session_status(session_id: int, status: str) -> None:
    init_session_db()
    status = status.strip().lower()
    if status not in {"waiting", "live", "paused", "closed"}:
        raise ValueError("Statut de session invalide.")
    if _pg():
        with get_connection() as conn:
            with conn.cursor() as cur:
                if status == "closed":
                    cur.execute("UPDATE training_sessions SET status = %s, closed_at = now() WHERE id = %s", (status, session_id))
                else:
                    cur.execute("UPDATE training_sessions SET status = %s WHERE id = %s", (status, session_id))
            conn.commit()
        return
    with get_connection() as conn:
        if status == "closed":
            conn.execute("UPDATE training_sessions SET status = ?, closed_at = CURRENT_TIMESTAMP WHERE id = ?", (status, session_id))
        else:
            conn.execute("UPDATE training_sessions SET status = ? WHERE id = ?", (status, session_id))
        conn.commit()


def update_session_position(session_id: int, current_question_index: int) -> None:
    init_session_db()
    session = get_training_session(session_id)
    if not session:
        return
    max_index = max(0, len(session.get("questions", [])) - 1)
    idx = max(0, min(int(current_question_index), max_index))
    if _pg():
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE training_sessions SET current_question_index = %s WHERE id = %s", (idx, session_id))
            conn.commit()
        return
    with get_connection() as conn:
        conn.execute("UPDATE training_sessions SET current_question_index = ? WHERE id = ?", (idx, session_id))
        conn.commit()


def set_session_show_correction(session_id: int, show_correction: bool) -> None:
    init_session_db()
    if _pg():
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE training_sessions SET show_correction = %s WHERE id = %s", (bool(show_correction), session_id))
            conn.commit()
        return
    with get_connection() as conn:
        conn.execute("UPDATE training_sessions SET show_correction = ? WHERE id = ?", (1 if show_correction else 0, session_id))
        conn.commit()


def join_training_session(session_id: int, learner_id: int) -> Dict[str, Any]:
    init_session_db()
    if _pg():
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO session_participants (session_id, learner_id)
                    VALUES (%s, %s)
                    ON CONFLICT (session_id, learner_id) DO NOTHING
                """, (session_id, learner_id))
                cur.execute("SELECT id, session_id, learner_id, joined_at FROM session_participants WHERE session_id = %s AND learner_id = %s", (session_id, learner_id))
                row = cur.fetchone()
            conn.commit()
        return _row(row)
    with get_connection() as conn:
        conn.execute("INSERT OR IGNORE INTO session_participants (session_id, learner_id) VALUES (?, ?)", (session_id, learner_id))
        conn.commit()
        row = conn.execute("SELECT id, session_id, learner_id, joined_at FROM session_participants WHERE session_id = ? AND learner_id = ?", (session_id, learner_id)).fetchone()
    return dict(row)


def list_session_participants(session_id: int) -> List[Dict[str, Any]]:
    init_session_db()
    if _pg():
        return _fetchall("""
            SELECT sp.id, sp.session_id, sp.learner_id, sp.joined_at, l.name, l.email, l.group_name
            FROM session_participants sp
            JOIN learners l ON l.id = sp.learner_id
            WHERE sp.session_id = %s
            ORDER BY sp.joined_at ASC
        """, (session_id,))
    return _fetchall("""
        SELECT sp.id, sp.session_id, sp.learner_id, sp.joined_at, l.name, l.email, l.group_name
        FROM session_participants sp
        JOIN learners l ON l.id = sp.learner_id
        WHERE sp.session_id = ?
        ORDER BY datetime(sp.joined_at) ASC
    """, (session_id,))


def save_session_answer(session_id: int, participant_id: int, learner_id: int, question_index: int, question: Dict[str, Any], user_answer: Any, correct_answer: Any, is_correct: Optional[bool], score: float, selected_feedback: str = "", correct_feedback: str = "") -> None:
    init_session_db()
    is_correct_db = None if is_correct is None else (bool(is_correct) if _pg() else (1 if is_correct else 0))
    values = (session_id, participant_id, learner_id, question_index, question.get("type", ""), question.get("question", ""), _json_value(user_answer), _json_value(correct_answer), is_correct_db, float(score), selected_feedback, correct_feedback)
    if _pg():
        sql = """
            INSERT INTO session_answers (
                session_id, participant_id, learner_id, question_index,
                question_type, question_text, user_answer_json, correct_answer_json,
                is_correct, score, selected_feedback, correct_feedback
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(session_id, participant_id, question_index)
            DO UPDATE SET
                user_answer_json = EXCLUDED.user_answer_json,
                correct_answer_json = EXCLUDED.correct_answer_json,
                is_correct = EXCLUDED.is_correct,
                score = EXCLUDED.score,
                selected_feedback = EXCLUDED.selected_feedback,
                correct_feedback = EXCLUDED.correct_feedback,
                answered_at = now()
        """
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, values)
            conn.commit()
        return
    sql = """
        INSERT INTO session_answers (
            session_id, participant_id, learner_id, question_index,
            question_type, question_text, user_answer_json, correct_answer_json,
            is_correct, score, selected_feedback, correct_feedback
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(session_id, participant_id, question_index)
        DO UPDATE SET
            user_answer_json = excluded.user_answer_json,
            correct_answer_json = excluded.correct_answer_json,
            is_correct = excluded.is_correct,
            score = excluded.score,
            selected_feedback = excluded.selected_feedback,
            correct_feedback = excluded.correct_feedback,
            answered_at = CURRENT_TIMESTAMP
    """
    with get_connection() as conn:
        conn.execute(sql, values)
        conn.commit()


def get_session_answer(session_id: int, participant_id: int, question_index: int) -> Optional[Dict[str, Any]]:
    init_session_db()
    if _pg():
        rows = _fetchall("SELECT * FROM session_answers WHERE session_id = %s AND participant_id = %s AND question_index = %s", (session_id, participant_id, question_index))
    else:
        rows = _fetchall("SELECT * FROM session_answers WHERE session_id = ? AND participant_id = ? AND question_index = ?", (session_id, participant_id, question_index))
    if not rows:
        return None
    data = rows[0]
    if data.get("is_correct") is not None:
        data["is_correct"] = bool(data["is_correct"])
    data["user_answer_json"] = _json_display(data.get("user_answer_json"))
    data["correct_answer_json"] = _json_display(data.get("correct_answer_json"))
    return data


def list_session_answers(session_id: int, question_index: Optional[int] = None) -> List[Dict[str, Any]]:
    init_session_db()
    if _pg():
        base = """
            SELECT sa.id, sa.session_id, sa.participant_id, sa.learner_id,
                   sa.question_index, sa.question_type, sa.question_text,
                   sa.user_answer_json, sa.correct_answer_json, sa.is_correct,
                   sa.score::float AS score, sa.selected_feedback, sa.correct_feedback,
                   sa.answered_at,
                   l.name AS learner_name, l.email AS learner_email, l.group_name
            FROM session_answers sa
            JOIN learners l ON l.id = sa.learner_id
            WHERE sa.session_id = %s
        """
        if question_index is None:
            rows = _fetchall(base + " ORDER BY sa.question_index ASC, sa.answered_at ASC", (session_id,))
        else:
            rows = _fetchall(base + " AND sa.question_index = %s ORDER BY sa.answered_at ASC", (session_id, question_index))
    else:
        base = """
            SELECT sa.*, l.name AS learner_name, l.email AS learner_email, l.group_name
            FROM session_answers sa
            JOIN learners l ON l.id = sa.learner_id
            WHERE sa.session_id = ?
        """
        if question_index is None:
            rows = _fetchall(base + " ORDER BY sa.question_index ASC, datetime(sa.answered_at) ASC", (session_id,))
        else:
            rows = _fetchall(base + " AND sa.question_index = ? ORDER BY datetime(sa.answered_at) ASC", (session_id, question_index))
    for item in rows:
        if item.get("is_correct") is not None:
            item["is_correct"] = bool(item["is_correct"])
        item["user_answer_json"] = _json_display(item.get("user_answer_json"))
        item["correct_answer_json"] = _json_display(item.get("correct_answer_json"))
    return rows


def get_session_live_stats(session_id: int, question_index: int) -> Dict[str, Any]:
    participants = list_session_participants(session_id)
    answers = list_session_answers(session_id, question_index=question_index)
    answer_count = len(answers)
    participant_count = len(participants)
    correct_count = len([a for a in answers if a.get("is_correct") is True])
    incorrect_count = len([a for a in answers if a.get("is_correct") is False])
    manual_count = len([a for a in answers if a.get("is_correct") is None])
    distribution: Dict[str, int] = {}
    for answer in answers:
        raw = answer.get("user_answer_json") or ""
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = raw
        key = "matching" if isinstance(parsed, dict) else str(parsed).strip().replace('"', "")
        distribution[key] = distribution.get(key, 0) + 1
    return {
        "participant_count": participant_count,
        "answer_count": answer_count,
        "correct_count": correct_count,
        "incorrect_count": incorrect_count,
        "manual_count": manual_count,
        "percent_answered": round((answer_count / participant_count) * 100, 1) if participant_count else 0,
        "percent_correct": round((correct_count / answer_count) * 100, 1) if answer_count else 0,
        "distribution": distribution,
        "answers": answers,
    }


def get_session_participant_summary(session_id: int) -> List[Dict[str, Any]]:
    participants = list_session_participants(session_id)
    answers = list_session_answers(session_id)
    by_participant: Dict[int, Dict[str, Any]] = {}
    for participant in participants:
        by_participant[participant["id"]] = {
            "participant_id": participant["id"],
            "learner_id": participant["learner_id"],
            "name": participant["name"],
            "email": participant["email"],
            "group_name": participant.get("group_name", ""),
            "score": 0.0,
            "max_score": 0.0,
            "answers": 0,
            "manual_count": 0,
        }
    for answer in answers:
        item = by_participant.get(answer["participant_id"])
        if not item:
            continue
        item["answers"] += 1
        if answer.get("is_correct") is None:
            item["manual_count"] += 1
        else:
            item["max_score"] += 1
            item["score"] += float(answer.get("score") or 0)
    for item in by_participant.values():
        item["percentage"] = round((item["score"] / item["max_score"]) * 100, 1) if item["max_score"] else 0.0
    return sorted(by_participant.values(), key=lambda x: (-x["percentage"], x["name"]))
