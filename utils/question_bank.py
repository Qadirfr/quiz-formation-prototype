from __future__ import annotations

import hashlib
import json
import random
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


def init_question_bank_db() -> None:
    if _pg():
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS question_bank (
                        id bigserial PRIMARY KEY,
                        question_hash text NOT NULL UNIQUE,
                        source_quiz_id bigint,
                        source_quiz_title text,
                        question_type text,
                        domain text,
                        subdomain text,
                        difficulty text,
                        cognitive_level text,
                        competency text,
                        concept_evaluated text,
                        question_text text NOT NULL,
                        question_json jsonb NOT NULL,
                        is_active boolean NOT NULL DEFAULT true,
                        created_at timestamptz NOT NULL DEFAULT now()
                    )
                """)
            conn.commit()
        return

    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS question_bank (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question_hash TEXT NOT NULL UNIQUE,
                source_quiz_id INTEGER,
                source_quiz_title TEXT,
                question_type TEXT,
                domain TEXT,
                subdomain TEXT,
                difficulty TEXT,
                cognitive_level TEXT,
                competency TEXT,
                concept_evaluated TEXT,
                question_text TEXT NOT NULL,
                question_json TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def make_question_hash(question: Dict[str, Any]) -> str:
    base = "|".join(
        [
            normalize_text(question.get("type", "")),
            normalize_text(question.get("question", "")),
            normalize_text(question.get("correct_answer", "")),
            normalize_text(json.dumps(question.get("pairs", []), ensure_ascii=False, sort_keys=True)),
        ]
    )
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def prepare_question(question: Dict[str, Any]) -> Dict[str, Any]:
    q = dict(question)
    q.setdefault("type", "single_choice")
    q.setdefault("domain", q.get("domaine", "") or "Non classé")
    q.setdefault("subdomain", q.get("sous_domaine", ""))
    q.setdefault("difficulty", "")
    q.setdefault("cognitive_level", q.get("niveau_cognitif", ""))
    q.setdefault("competency", q.get("competence", ""))
    q.setdefault("concept_evaluated", "")
    q.setdefault("question", "")
    q.setdefault("options", [])
    q.setdefault("pairs", [])
    q.setdefault("correct_answer", "")
    q.setdefault("explanation", "")
    q.setdefault("feedbacks", {})
    q.setdefault("remediation", q.get("piste_de_revision", ""))
    return q


def add_question_to_bank(
    question: Dict[str, Any],
    source_quiz_id: Optional[int] = None,
    source_quiz_title: str = "",
) -> bool:
    init_question_bank_db()
    q = prepare_question(question)
    if not q.get("question"):
        return False

    question_hash = make_question_hash(q)
    values = (
        question_hash,
        source_quiz_id,
        source_quiz_title,
        q.get("type", ""),
        q.get("domain", "") or "Non classé",
        q.get("subdomain", ""),
        q.get("difficulty", ""),
        q.get("cognitive_level", ""),
        q.get("competency", ""),
        q.get("concept_evaluated", ""),
        q.get("question", ""),
        _json_db(q),
    )

    if _pg():
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO question_bank (
                        question_hash, source_quiz_id, source_quiz_title,
                        question_type, domain, subdomain, difficulty,
                        cognitive_level, competency, concept_evaluated,
                        question_text, question_json, is_active
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, true)
                    ON CONFLICT (question_hash) DO NOTHING
                    RETURNING id
                """, values)
                row = cur.fetchone()
            conn.commit()
        return row is not None

    with get_connection() as conn:
        cursor = conn.execute("""
            INSERT OR IGNORE INTO question_bank (
                question_hash, source_quiz_id, source_quiz_title,
                question_type, domain, subdomain, difficulty,
                cognitive_level, competency, concept_evaluated,
                question_text, question_json, is_active
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        """, values)
        conn.commit()
        return cursor.rowcount > 0


def add_quiz_to_bank(quiz: Dict[str, Any], source_quiz_id: Optional[int] = None) -> Dict[str, int]:
    title = quiz.get("quiz_title", "") if isinstance(quiz, dict) else ""
    questions = quiz.get("questions", []) if isinstance(quiz, dict) else []

    added = 0
    ignored = 0
    for question in questions:
        if not isinstance(question, dict):
            ignored += 1
            continue
        if add_question_to_bank(question, source_quiz_id=source_quiz_id, source_quiz_title=title):
            added += 1
        else:
            ignored += 1

    return {"added": added, "ignored": ignored, "total": len(questions)}


def _group_count(field: str) -> List[Dict[str, Any]]:
    allowed = {
        "domain",
        "subdomain",
        "difficulty",
        "cognitive_level",
        "question_type",
        "source_quiz_title",
    }
    if field not in allowed:
        raise ValueError("Champ non autorisé.")

    if _pg():
        sql = f"""
            SELECT COALESCE(NULLIF({field}, ''), 'Non renseigné') AS label, COUNT(*) AS count
            FROM question_bank
            WHERE is_active = true
            GROUP BY COALESCE(NULLIF({field}, ''), 'Non renseigné')
            ORDER BY count DESC, label ASC
        """
    else:
        sql = f"""
            SELECT COALESCE(NULLIF({field}, ''), 'Non renseigné') AS label, COUNT(*) AS count
            FROM question_bank
            WHERE is_active = 1
            GROUP BY COALESCE(NULLIF({field}, ''), 'Non renseigné')
            ORDER BY count DESC, label ASC
        """
    return _fetchall(sql)


def get_question_bank_stats() -> Dict[str, Any]:
    init_question_bank_db()
    if _pg():
        rows = _fetchall("SELECT COUNT(*) AS c FROM question_bank WHERE is_active = true")
    else:
        rows = _fetchall("SELECT COUNT(*) AS c FROM question_bank WHERE is_active = 1")
    total = int(rows[0]["c"]) if rows else 0
    return {
        "total": total,
        "by_domain": _group_count("domain"),
        "by_difficulty": _group_count("difficulty"),
        "by_cognitive_level": _group_count("cognitive_level"),
        "by_type": _group_count("question_type"),
    }


def list_bank_domains() -> List[str]:
    init_question_bank_db()
    if _pg():
        rows = _fetchall("""
            SELECT DISTINCT COALESCE(NULLIF(domain, ''), 'Non classé') AS domain
            FROM question_bank
            WHERE is_active = true
            ORDER BY domain ASC
        """)
    else:
        rows = _fetchall("""
            SELECT DISTINCT COALESCE(NULLIF(domain, ''), 'Non classé') AS domain
            FROM question_bank
            WHERE is_active = 1
            ORDER BY domain ASC
        """)
    return [row["domain"] for row in rows]


def list_bank_difficulties() -> List[str]:
    init_question_bank_db()
    if _pg():
        rows = _fetchall("""
            SELECT DISTINCT COALESCE(NULLIF(difficulty, ''), 'Non renseigné') AS difficulty
            FROM question_bank
            WHERE is_active = true
            ORDER BY difficulty ASC
        """)
    else:
        rows = _fetchall("""
            SELECT DISTINCT COALESCE(NULLIF(difficulty, ''), 'Non renseigné') AS difficulty
            FROM question_bank
            WHERE is_active = 1
            ORDER BY difficulty ASC
        """)
    return [row["difficulty"] for row in rows]


def _question_from_row(row: Dict[str, Any]) -> Dict[str, Any]:
    q = _json_load(row["question_json"]) or {}
    q["_bank_id"] = row["id"]
    return q


def select_random_questions(
    limit: int = 40,
    domain: str = "",
    difficulty: str = "",
    exclude_ids: Optional[List[int]] = None,
) -> List[Dict[str, Any]]:
    init_question_bank_db()
    exclude_ids = exclude_ids or []

    if _pg():
        clauses = ["is_active = true"]
        params: List[Any] = []

        if domain and domain != "Tous":
            clauses.append("COALESCE(NULLIF(domain, ''), 'Non classé') = %s")
            params.append(domain)

        if difficulty and difficulty != "Tous":
            clauses.append("COALESCE(NULLIF(difficulty, ''), 'Non renseigné') = %s")
            params.append(difficulty)

        if exclude_ids:
            placeholders = ",".join(["%s"] * len(exclude_ids))
            clauses.append(f"id NOT IN ({placeholders})")
            params.extend(exclude_ids)

        where = " AND ".join(clauses)
        rows = _fetchall(
            f"""
            SELECT id, question_json
            FROM question_bank
            WHERE {where}
            ORDER BY RANDOM()
            LIMIT %s
            """,
            (*params, int(limit)),
        )
        return [_question_from_row(row) for row in rows]

    clauses = ["is_active = 1"]
    params: List[Any] = []

    if domain and domain != "Tous":
        clauses.append("COALESCE(NULLIF(domain, ''), 'Non classé') = ?")
        params.append(domain)

    if difficulty and difficulty != "Tous":
        clauses.append("COALESCE(NULLIF(difficulty, ''), 'Non renseigné') = ?")
        params.append(difficulty)

    if exclude_ids:
        placeholders = ",".join("?" for _ in exclude_ids)
        clauses.append(f"id NOT IN ({placeholders})")
        params.extend(exclude_ids)

    where = " AND ".join(clauses)
    rows = _fetchall(
        f"""
        SELECT id, question_json
        FROM question_bank
        WHERE {where}
        ORDER BY RANDOM()
        LIMIT ?
        """,
        (*params, int(limit)),
    )
    return [_question_from_row(row) for row in rows]


def get_learner_weaknesses(email: str, limit: int = 5) -> Dict[str, List[str]]:
    clean_email = email.strip().lower()
    if not clean_email:
        return {"domains": [], "cognitive_levels": []}

    try:
        if _pg():
            domain_rows = _fetchall("""
                SELECT COALESCE(NULLIF(la.domain, ''), 'Non classé') AS label,
                       COUNT(*) AS wrong_count
                FROM learner_answers la
                JOIN quiz_attempts qa ON qa.id = la.attempt_id
                JOIN learners l ON l.id = qa.learner_id
                WHERE lower(l.email) = %s AND la.is_correct = false
                GROUP BY COALESCE(NULLIF(la.domain, ''), 'Non classé')
                ORDER BY wrong_count DESC
                LIMIT %s
            """, (clean_email, limit))
            cognitive_rows = _fetchall("""
                SELECT COALESCE(NULLIF(la.cognitive_level, ''), 'Non renseigné') AS label,
                       COUNT(*) AS wrong_count
                FROM learner_answers la
                JOIN quiz_attempts qa ON qa.id = la.attempt_id
                JOIN learners l ON l.id = qa.learner_id
                WHERE lower(l.email) = %s AND la.is_correct = false
                GROUP BY COALESCE(NULLIF(la.cognitive_level, ''), 'Non renseigné')
                ORDER BY wrong_count DESC
                LIMIT %s
            """, (clean_email, limit))
        else:
            domain_rows = _fetchall("""
                SELECT COALESCE(NULLIF(la.domain, ''), 'Non classé') AS label,
                       COUNT(*) AS wrong_count
                FROM learner_answers la
                JOIN quiz_attempts qa ON qa.id = la.attempt_id
                JOIN learners l ON l.id = qa.learner_id
                WHERE lower(l.email) = ? AND la.is_correct = 0
                GROUP BY COALESCE(NULLIF(la.domain, ''), 'Non classé')
                ORDER BY wrong_count DESC
                LIMIT ?
            """, (clean_email, limit))
            cognitive_rows = _fetchall("""
                SELECT COALESCE(NULLIF(la.cognitive_level, ''), 'Non renseigné') AS label,
                       COUNT(*) AS wrong_count
                FROM learner_answers la
                JOIN quiz_attempts qa ON qa.id = la.attempt_id
                JOIN learners l ON l.id = qa.learner_id
                WHERE lower(l.email) = ? AND la.is_correct = 0
                GROUP BY COALESCE(NULLIF(la.cognitive_level, ''), 'Non renseigné')
                ORDER BY wrong_count DESC
                LIMIT ?
            """, (clean_email, limit))
    except Exception:
        return {"domains": [], "cognitive_levels": []}

    return {
        "domains": [row["label"] for row in domain_rows if row["label"] != "Non classé"],
        "cognitive_levels": [row["label"] for row in cognitive_rows if row["label"] != "Non renseigné"],
    }


def select_adaptive_questions(
    learner_email: str,
    limit: int = 40,
    domain: str = "",
    difficulty: str = "",
) -> List[Dict[str, Any]]:
    init_question_bank_db()
    limit = int(limit)
    weaknesses = get_learner_weaknesses(learner_email)

    selected: List[Dict[str, Any]] = []
    selected_ids: List[int] = []

    target_weak_count = max(1, int(limit * 0.7))
    weak_domains = weaknesses.get("domains", [])

    if weak_domains and not domain:
        per_domain = max(1, target_weak_count // len(weak_domains))
        for weak_domain in weak_domains:
            qs = select_random_questions(
                limit=per_domain,
                domain=weak_domain,
                difficulty=difficulty,
                exclude_ids=selected_ids,
            )
            selected.extend(qs)
            selected_ids.extend([q.get("_bank_id") for q in qs if q.get("_bank_id")])

    if domain and domain != "Tous":
        selected = select_random_questions(limit=limit, domain=domain, difficulty=difficulty)
        return selected

    remaining = max(0, limit - len(selected))
    if remaining:
        selected.extend(
            select_random_questions(
                limit=remaining,
                domain="",
                difficulty=difficulty,
                exclude_ids=selected_ids,
            )
        )

    random.shuffle(selected)
    return selected[:limit]


def build_quiz_from_bank(
    questions: List[Dict[str, Any]],
    title: str,
    mode: str = "random",
    learner_email: str = "",
) -> Dict[str, Any]:
    cleaned_questions = []
    for question in questions:
        q = dict(question)
        q.pop("_bank_id", None)
        cleaned_questions.append(q)

    return {
        "quiz_title": title,
        "questions": cleaned_questions,
        "analysis_summary": f"Quiz créé depuis la banque de questions. Mode : {mode}.",
        "quality_summary": {
            "average_score": 0,
            "low_quality_count": 0,
            "warning": "Quiz construit par sélection dans la banque de questions.",
        },
        "note": "Quiz généré depuis la banque de questions locale ou Supabase.",
        "selection_mode": mode,
        "learner_email": learner_email,
    }


def get_question_bank_source_stats() -> List[Dict[str, Any]]:
    init_question_bank_db()
    if _pg():
        rows = _fetchall("""
            SELECT COALESCE(NULLIF(source_quiz_title, ''), 'Non renseigné') AS label,
                   COUNT(*) AS count
            FROM question_bank
            WHERE is_active = true
            GROUP BY COALESCE(NULLIF(source_quiz_title, ''), 'Non renseigné')
            ORDER BY count DESC, label ASC
        """)
    else:
        rows = _fetchall("""
            SELECT COALESCE(NULLIF(source_quiz_title, ''), 'Non renseigné') AS label,
                   COUNT(*) AS count
            FROM question_bank
            WHERE is_active = 1
            GROUP BY COALESCE(NULLIF(source_quiz_title, ''), 'Non renseigné')
            ORDER BY count DESC, label ASC
        """)
    return [{"label": row["label"], "count": row["count"]} for row in rows]
