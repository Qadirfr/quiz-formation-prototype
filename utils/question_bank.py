from __future__ import annotations

import hashlib
import json
import random
from functools import lru_cache
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


@lru_cache(maxsize=1)
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

def list_bank_sources() -> List[str]:
    init_question_bank_db()
    if _pg():
        rows = _fetchall("""
            SELECT COALESCE(NULLIF(source_quiz_title, ''), 'Non renseigné') AS label
            FROM question_bank
            WHERE is_active = true
            GROUP BY COALESCE(NULLIF(source_quiz_title, ''), 'Non renseigné')
            ORDER BY label ASC
        """)
    else:
        rows = _fetchall("""
            SELECT COALESCE(NULLIF(source_quiz_title, ''), 'Non renseigné') AS label
            FROM question_bank
            WHERE is_active = 1
            GROUP BY COALESCE(NULLIF(source_quiz_title, ''), 'Non renseigné')
            ORDER BY label ASC
        """)
    return [row["label"] for row in rows if row.get("label")]


def select_random_questions_scoped(
    limit: int,
    domain: str = "",
    difficulty: str = "",
    source_quiz_title: str = "",
    question_type: str = "",
) -> List[Dict[str, Any]]:
    init_question_bank_db()
    placeholder = "%s" if _pg() else "?"
    active_cond = "is_active = true" if _pg() else "is_active = 1"

    where = [active_cond]
    params: List[Any] = []

    if domain:
        where.append(f"domain = {placeholder}")
        params.append(domain)
    if difficulty:
        where.append(f"difficulty = {placeholder}")
        params.append(difficulty)
    if source_quiz_title:
        if source_quiz_title == "Non renseigné":
            where.append("(source_quiz_title IS NULL OR source_quiz_title = '')")
        else:
            where.append(f"source_quiz_title = {placeholder}")
            params.append(source_quiz_title)
    if question_type:
        where.append(f"question_type = {placeholder}")
        params.append(question_type)

    params.append(int(limit))

    rows = _fetchall(
        f"""
        SELECT question_json
        FROM question_bank
        WHERE {" AND ".join(where)}
        ORDER BY RANDOM()
        LIMIT {placeholder}
        """,
        tuple(params),
    )

    questions: List[Dict[str, Any]] = []
    for row in rows:
        raw = row.get("question_json")
        if isinstance(raw, dict):
            questions.append(raw)
        else:
            questions.append(json.loads(raw))
    return questions

# ---------------------------------------------------------------------------
# V21.8 - Mélange stable des propositions QCM
# ---------------------------------------------------------------------------
# Objectif :
# - mélanger les options des QCM une seule fois au moment où les questions
#   sont sélectionnées / construites ;
# - conserver un ordre stable pendant la tentative ;
# - préserver les champs de correction si la bonne réponse est stockée en A/B/C/D
#   ou en index numérique ;
# - éviter true_false, matching et short_answer.
# ---------------------------------------------------------------------------

def _v21_8_option_text(option):
    import json as _json

    if isinstance(option, dict):
        for key in ("label", "text", "value", "answer", "option"):
            value = option.get(key)
            if value not in (None, ""):
                return str(value)
        return _json.dumps(option, ensure_ascii=False, sort_keys=True)
    return str(option)


def _v21_8_is_shuffle_candidate(question):
    qtype = str(question.get("type") or question.get("question_type") or "").lower().strip()
    if any(token in qtype for token in ("true_false", "vrai", "faux", "matching", "appariement", "short", "courte", "open")):
        return False

    options = question.get("options")
    return isinstance(options, list) and len(options) >= 3


def _v21_8_shuffle_one_question(question, salt=""):
    import copy as _copy
    import hashlib as _hashlib
    import random as _random
    import re as _re

    if not isinstance(question, dict):
        return question

    if question.get("_v21_8_options_shuffled"):
        return question

    if not _v21_8_is_shuffle_candidate(question):
        return _copy.deepcopy(question)

    q = _copy.deepcopy(question)
    options = list(q.get("options") or [])

    if len(options) < 3:
        return q

    seed_payload = "|".join([
        str(q.get("id") or q.get("question_id") or ""),
        str(q.get("question") or q.get("question_text") or ""),
        str(q.get("domain") or ""),
        str(q.get("difficulty") or ""),
        str(salt or ""),
    ])
    seed = int(_hashlib.sha256(seed_payload.encode("utf-8")).hexdigest()[:16], 16)

    indexed = list(enumerate(options))
    rng = _random.Random(seed)
    rng.shuffle(indexed)

    # Si le hasard redonne exactement le même ordre, on décale légèrement
    # pour casser les biais A/B/C/D sans rendre l'ordre instable.
    if [old_idx for old_idx, _ in indexed] == list(range(len(options))) and len(indexed) > 1:
        indexed = indexed[1:] + indexed[:1]

    old_to_new_index = {old_idx: new_idx for new_idx, (old_idx, _) in enumerate(indexed)}
    letters = [chr(ord("A") + i) for i in range(len(options))]
    old_to_new_letter = {
        letters[old_idx]: letters[new_idx]
        for old_idx, new_idx in old_to_new_index.items()
        if old_idx < len(letters) and new_idx < len(letters)
    }

    q["options"] = [option for _, option in indexed]

    def transform_answer_value(value):
        if isinstance(value, list):
            return [transform_answer_value(item) for item in value]

        if isinstance(value, tuple):
            return tuple(transform_answer_value(item) for item in value)

        if isinstance(value, int):
            return old_to_new_index.get(value, value)

        if isinstance(value, str):
            stripped = value.strip()
            upper = stripped.upper()

            # Cas "A", "B", "C", "D"
            if upper in old_to_new_letter:
                return old_to_new_letter[upper]

            # Cas "0", "1", "2", "3"
            if _re.fullmatch(r"\d+", stripped):
                index_value = int(stripped)
                if index_value in old_to_new_index:
                    return str(old_to_new_index[index_value])

            # Cas texte de réponse : on ne modifie pas, car le texte reste identique.
            return value

        return value

    # Champs fréquents de correction. Le script reste prudent :
    # il ne modifie que les lettres / index, pas les textes.
    for field in (
        "correct_answer",
        "answer",
        "correct_option",
        "correct_options",
        "correct_index",
        "correct_indices",
        "correct_value",
        "correct_values",
        "correctValues",
    ):
        if field in q:
            q[field] = transform_answer_value(q[field])

    # Remappage des feedback_a / feedback_b / feedback_c / feedback_d
    old_feedbacks = {}
    for idx, letter in enumerate(letters):
        key = f"feedback_{letter.lower()}"
        if key in q:
            old_feedbacks[idx] = q.get(key)

    if old_feedbacks:
        for new_idx, (old_idx, _) in enumerate(indexed):
            old_value = old_feedbacks.get(old_idx)
            if new_idx < len(letters):
                q[f"feedback_{letters[new_idx].lower()}"] = old_value

    # Remappage d'un dictionnaire feedbacks si les clés sont A/B/C/D.
    feedbacks = q.get("feedbacks")
    if isinstance(feedbacks, dict):
        new_feedbacks = {}
        for key, value in feedbacks.items():
            key_upper = str(key).strip().upper()
            if key_upper in old_to_new_letter:
                new_feedbacks[old_to_new_letter[key_upper]] = value
            else:
                new_feedbacks[key] = value
        q["feedbacks"] = new_feedbacks

    q["_v21_8_options_shuffled"] = True
    return q


def shuffle_qcm_options_stably(questions, salt=""):
    if not isinstance(questions, list):
        return questions
    return [
        _v21_8_shuffle_one_question(question, salt=f"{salt}|{index}")
        for index, question in enumerate(questions)
    ]


if not globals().get("_V21_8_QCM_SHUFFLE_WRAPPERS_ACTIVE"):
    _V21_8_QCM_SHUFFLE_WRAPPERS_ACTIVE = True

    try:
        _v21_8_original_select_random_questions = select_random_questions

        def select_random_questions(*args, **kwargs):
            questions = _v21_8_original_select_random_questions(*args, **kwargs)
            return shuffle_qcm_options_stably(
                questions,
                salt=f"select_random_questions|{args}|{sorted(kwargs.items())}",
            )
    except NameError:
        pass

    try:
        _v21_8_original_select_random_questions_scoped = select_random_questions_scoped

        def select_random_questions_scoped(*args, **kwargs):
            questions = _v21_8_original_select_random_questions_scoped(*args, **kwargs)
            return shuffle_qcm_options_stably(
                questions,
                salt=f"select_random_questions_scoped|{args}|{sorted(kwargs.items())}",
            )
    except NameError:
        pass

    try:
        _v21_8_original_select_adaptive_questions = select_adaptive_questions

        def select_adaptive_questions(*args, **kwargs):
            questions = _v21_8_original_select_adaptive_questions(*args, **kwargs)
            return shuffle_qcm_options_stably(
                questions,
                salt=f"select_adaptive_questions|{args}|{sorted(kwargs.items())}",
            )
    except NameError:
        pass

    try:
        _v21_8_original_build_quiz_from_bank = build_quiz_from_bank

        def build_quiz_from_bank(questions, *args, **kwargs):
            title = kwargs.get("title") or (args[0] if args else "")
            shuffled_questions = shuffle_qcm_options_stably(
                questions,
                salt=f"build_quiz_from_bank|{title}",
            )
            return _v21_8_original_build_quiz_from_bank(shuffled_questions, *args, **kwargs)
    except NameError:
        pass


# ---------------------------------------------------------------------------
# V23 TAXONOMIE BANQUE DE QUESTIONS - OVERRIDES
# ---------------------------------------------------------------------------
# Ce bloc surcharge certaines fonctions historiques sans supprimer l'ancien code.
# Il ajoute une couche propre :
#   training_scope    = CDPO / Naturalisation civique / Autre
#   question_set_type = Examen blanc / Pré-assessment / Banque autonome / ...
#
# L'objectif est d'éviter que source_quiz_title soit utilisé comme périmètre.


### V23 TAXONOMIE BANQUE DE QUESTIONS - OVERRIDES ###

def _v23_normalize_text(value):
    import unicodedata

    value = value or ""
    value = unicodedata.normalize("NFKD", str(value))
    value = "".join(c for c in value if not unicodedata.combining(c))
    return value.lower().strip()


def infer_training_scope_from_bank(source_quiz_title="", domain=""):
    title = _v23_normalize_text(source_quiz_title)
    dom = _v23_normalize_text(domain)

    if title.startswith("cdpo") or " cdpo" in title:
        return "CDPO"

    naturalisation_domains = {
        "institutions francaises",
        "principes et valeurs de la republique",
        "histoire, geographie et culture",
        "vie en societe",
        "droits et devoirs",
        "naturalisation et integration",
    }

    if "naturalisation" in title or dom in naturalisation_domains:
        return "Naturalisation civique"

    return "Autre"


def infer_question_set_type_from_bank(source_quiz_title=""):
    title = _v23_normalize_text(source_quiz_title)

    if "examen blanc" in title:
        return "Examen blanc"
    if "pre-assessment" in title or "pre assessment" in title:
        return "Pré-assessment"
    if "entrainement domaine" in title:
        return "Entraînement par domaine"
    if "renforcement sous-domaines" in title or "renforcement sous domaines" in title:
        return "Renforcement sous-domaines"
    if "banque autonome" in title:
        return "Banque autonome"
    if "naturalisation" in title:
        return "Examen civique"

    return "Autre"


@lru_cache(maxsize=1)
def init_question_bank_db() -> None:
    """Initialise question_bank avec la taxonomie V23.

    Cette version reste compatible SQLite et PostgreSQL/Supabase.
    Elle crée les nouvelles colonnes si la table existe déjà.
    """
    if _pg():
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS question_bank (
                        id bigserial PRIMARY KEY,
                        question_hash text NOT NULL UNIQUE,
                        source_quiz_id bigint,
                        source_quiz_title text,
                        training_scope text,
                        question_set_type text,
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
                cur.execute("ALTER TABLE question_bank ADD COLUMN IF NOT EXISTS training_scope text")
                cur.execute("ALTER TABLE question_bank ADD COLUMN IF NOT EXISTS question_set_type text")
        return

    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS question_bank (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question_hash TEXT NOT NULL UNIQUE,
                source_quiz_id INTEGER,
                source_quiz_title TEXT,
                training_scope TEXT,
                question_set_type TEXT,
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
        columns = [row[1] for row in conn.execute("PRAGMA table_info(question_bank)").fetchall()]
        if "training_scope" not in columns:
            conn.execute("ALTER TABLE question_bank ADD COLUMN training_scope TEXT")
        if "question_set_type" not in columns:
            conn.execute("ALTER TABLE question_bank ADD COLUMN question_set_type TEXT")
        conn.commit()


def add_question_to_bank(question, source_quiz_id=None, source_quiz_title="") -> bool:
    """Ajoute une question avec les colonnes de taxonomie V23."""
    init_question_bank_db()
    q = prepare_question(question)
    if not q.get("question"):
        return False

    training_scope = (
        q.get("training_scope")
        or infer_training_scope_from_bank(source_quiz_title, q.get("domain", ""))
    )
    question_set_type = (
        q.get("question_set_type")
        or infer_question_set_type_from_bank(source_quiz_title)
    )

    q["training_scope"] = training_scope
    q["question_set_type"] = question_set_type

    question_hash = make_question_hash(q)
    values = (
        question_hash,
        source_quiz_id,
        source_quiz_title,
        training_scope,
        question_set_type,
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
                        training_scope, question_set_type,
                        question_type, domain, subdomain, difficulty,
                        cognitive_level, competency, concept_evaluated,
                        question_text, question_json, is_active
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, true)
                    ON CONFLICT (question_hash) DO NOTHING
                    RETURNING id
                """, values)
                row = cur.fetchone()
        return row is not None

    with get_connection() as conn:
        cursor = conn.execute("""
            INSERT OR IGNORE INTO question_bank (
                question_hash, source_quiz_id, source_quiz_title,
                training_scope, question_set_type,
                question_type, domain, subdomain, difficulty,
                cognitive_level, competency, concept_evaluated,
                question_text, question_json, is_active
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        """, values)
        conn.commit()
        return cursor.rowcount > 0


def _v23_group_count(field):
    allowed = {
        "training_scope",
        "question_set_type",
        "source_quiz_title",
        "domain",
        "subdomain",
        "difficulty",
        "cognitive_level",
        "question_type",
    }
    if field not in allowed:
        raise ValueError("Champ non autorisé.")

    active_cond = "is_active = true" if _pg() else "is_active = 1"
    sql = f"""
        SELECT COALESCE(NULLIF({field}, ''), 'Non renseigné') AS label, COUNT(*) AS count
        FROM question_bank
        WHERE {active_cond}
        GROUP BY COALESCE(NULLIF({field}, ''), 'Non renseigné')
        ORDER BY count DESC, label ASC
    """
    return _fetchall(sql)


def get_question_bank_stats():
    init_question_bank_db()
    active_cond = "is_active = true" if _pg() else "is_active = 1"
    rows = _fetchall(f"SELECT COUNT(*) AS c FROM question_bank WHERE {active_cond}")
    total = int(rows[0]["c"]) if rows else 0
    return {
        "total": total,
        "by_training_scope": _v23_group_count("training_scope"),
        "by_question_set_type": _v23_group_count("question_set_type"),
        "by_source_quiz_title": _v23_group_count("source_quiz_title"),
        "by_domain": _v23_group_count("domain"),
        "by_subdomain": _v23_group_count("subdomain"),
        "by_difficulty": _v23_group_count("difficulty"),
        "by_cognitive_level": _v23_group_count("cognitive_level"),
        "by_type": _v23_group_count("question_type"),
    }


def _v23_list_bank_values(field, default_label="Non renseigné"):
    allowed = {
        "training_scope",
        "question_set_type",
        "source_quiz_title",
        "domain",
        "subdomain",
        "difficulty",
        "question_type",
    }
    if field not in allowed:
        raise ValueError("Champ non autorisé.")

    active_cond = "is_active = true" if _pg() else "is_active = 1"
    placeholder = "%s" if _pg() else "?"
    rows = _fetchall(f"""
        SELECT DISTINCT COALESCE(NULLIF({field}, ''), {placeholder}) AS label
        FROM question_bank
        WHERE {active_cond}
        ORDER BY label ASC
    """, (default_label,))

    return [row["label"] for row in rows if row.get("label")]


def list_bank_training_scopes():
    init_question_bank_db()
    values = _v23_list_bank_values("training_scope", "Non renseigné")
    preferred = [v for v in ["CDPO", "Naturalisation civique"] if v in values]
    rest = [v for v in values if v not in preferred]
    return preferred + rest


def list_bank_question_set_types():
    init_question_bank_db()
    values = _v23_list_bank_values("question_set_type", "Non renseigné")
    preferred = [
        "Examen blanc",
        "Pré-assessment",
        "Banque autonome",
        "Entraînement par domaine",
        "Renforcement sous-domaines",
        "Examen civique",
    ]
    ordered = [v for v in preferred if v in values]
    rest = [v for v in values if v not in ordered]
    return ordered + rest


def list_bank_subdomains():
    init_question_bank_db()
    return _v23_list_bank_values("subdomain", "Non renseigné")


def list_bank_question_types():
    init_question_bank_db()
    return _v23_list_bank_values("question_type", "Non renseigné")


def list_question_bank_records_for_audit(
    include_inactive: bool = True,
    limit: int = 5000,
) -> List[Dict[str, Any]]:
    """Retourne les questions de la banque avec leur JSON pour audit en lecture seule."""
    init_question_bank_db()
    placeholder = "%s" if _pg() else "?"
    where = ""
    if not include_inactive:
        where = "WHERE is_active = true" if _pg() else "WHERE is_active = 1"

    rows = _fetchall(
        f"""
        SELECT
            id,
            source_quiz_id,
            source_quiz_title,
            training_scope,
            question_set_type,
            question_type,
            domain,
            subdomain,
            difficulty,
            cognitive_level,
            competency,
            concept_evaluated,
            question_text,
            question_json,
            is_active,
            created_at
        FROM question_bank
        {where}
        ORDER BY id ASC
        LIMIT {placeholder}
        """,
        (int(limit),),
    )

    result: List[Dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["question_json"] = _json_load(item.get("question_json")) or {}
        item["is_active"] = bool(item.get("is_active"))
        result.append(item)
    return result


def _v23_add_filter(where, params, field, value, placeholder, empty_label=None):
    if not value or value == "Tous":
        return

    if empty_label and value == empty_label:
        where.append(f"({field} IS NULL OR {field} = '')")
        return

    where.append(f"{field} = {placeholder}")
    params.append(value)


def _v23_question_from_row(row):
    payload = row.get("question_json")
    if isinstance(payload, dict):
        q = dict(payload)
    else:
        q = _json_load(payload) or {}

    q["_bank_id"] = row.get("id")

    for field in [
        "training_scope",
        "question_set_type",
        "source_quiz_title",
        "domain",
        "subdomain",
        "difficulty",
        "question_type",
    ]:
        if field in row and row.get(field) not in (None, ""):
            q.setdefault(field, row.get(field))

    return q


def select_random_questions_scoped(
    limit,
    domain="",
    difficulty="",
    source_quiz_title="",
    question_type="",
    training_scope="",
    question_set_type="",
    subdomain="",
):
    init_question_bank_db()

    placeholder = "%s" if _pg() else "?"
    active_cond = "is_active = true" if _pg() else "is_active = 1"

    where = [active_cond]
    params = []

    _v23_add_filter(where, params, "training_scope", training_scope, placeholder, "Non renseigné")
    _v23_add_filter(where, params, "question_set_type", question_set_type, placeholder, "Non renseigné")
    _v23_add_filter(where, params, "source_quiz_title", source_quiz_title, placeholder, "Non renseigné")
    _v23_add_filter(where, params, "domain", domain, placeholder, "Non classé")
    _v23_add_filter(where, params, "subdomain", subdomain, placeholder, "Non renseigné")
    _v23_add_filter(where, params, "difficulty", difficulty, placeholder, "Non renseigné")
    _v23_add_filter(where, params, "question_type", question_type, placeholder, "Non renseigné")

    params.append(int(limit))

    rows = _fetchall(
        f"""
        SELECT
            id,
            question_json,
            training_scope,
            question_set_type,
            source_quiz_title,
            domain,
            subdomain,
            difficulty,
            question_type
        FROM question_bank
        WHERE {" AND ".join(where)}
        ORDER BY RANDOM()
        LIMIT {placeholder}
        """,
        tuple(params),
    )

    return [_v23_question_from_row(row) for row in rows]

