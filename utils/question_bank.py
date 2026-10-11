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
            question_hash,
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


def _build_schema_audit_row_for_bank_record(row: Dict[str, Any]) -> Dict[str, Any]:
    """Construit la même ligne d'audit que l'interface pour une question de banque."""
    from utils.question_schema import audit_action, classify_question

    question = row.get("question_json") or {}
    audit = classify_question(question)
    issues = list(audit.get("issues") or [])

    db_type = str(row.get("question_type") or "")
    detected_type = audit.get("detected_type") or "unknown"
    if db_type and db_type != detected_type:
        conflict = f"db_type_conflict:{db_type}->{detected_type}"
        if conflict not in issues:
            issues.append(conflict)

    audit_row = {
        "source_kind": "Banque",
        "source_id": row.get("id"),
        "source_title": row.get("source_quiz_title") or "",
        "question_index": "",
        "active": bool(row.get("is_active")),
        "training_scope": row.get("training_scope") or "",
        "question_set_type": row.get("question_set_type") or "",
        "domain": row.get("domain") or "",
        "subdomain": row.get("subdomain") or "",
        "declared_type": audit.get("declared_type") or db_type,
        "detected_type": detected_type,
        "confidence": audit.get("confidence") or "",
        "needs_review": bool(audit.get("needs_review")) or bool(issues),
        "issues": issues,
        "question_preview": audit.get("question_preview") or "",
        "suggested_patch": audit.get("suggested_patch") or {},
    }
    audit_row["audit_action"] = audit_action(audit_row)
    return audit_row


def build_safe_cdpo_migration_preview(limit: int = 5000) -> Dict[str, Any]:
    """Prépare une migration sûre en lecture seule pour la banque CDPO active.

    La fonction ne retient que les questions réellement signalées à revoir,
    classées comme safe_candidate par le moteur d'audit. Les quiz sauvegardés
    ne sont jamais modifiés ici.
    """
    records = list_question_bank_records_for_audit(
        include_inactive=False,
        limit=limit,
    )
    hash_rows = _fetchall("SELECT id, question_hash FROM question_bank")
    existing_hash_owner = {
        str(row.get("question_hash") or ""): int(row.get("id"))
        for row in hash_rows
        if row.get("question_hash")
    }

    raw_candidates: List[Dict[str, Any]] = []
    for row in records:
        if not bool(row.get("is_active")):
            continue
        if str(row.get("training_scope") or "").strip().upper() != "CDPO":
            continue

        audit_row = _build_schema_audit_row_for_bank_record(row)
        if not audit_row.get("needs_review"):
            continue
        if audit_row.get("audit_action") != "safe_candidate":
            continue

        question = dict(row.get("question_json") or {})
        detected_type = str(audit_row.get("detected_type") or "")
        if not detected_type:
            continue

        patch = dict(audit_row.get("suggested_patch") or {})
        new_question = dict(question)
        new_question.update(patch)
        new_question["type"] = detected_type
        new_question["schema_version"] = int(
            new_question.get("schema_version") or 2
        )

        old_json_type = str(question.get("type") or "")
        db_type = str(row.get("question_type") or "")
        old_schema_version = question.get("schema_version")
        if (
            db_type == detected_type
            and old_json_type == detected_type
            and old_schema_version == 2
        ):
            continue

        new_hash = make_question_hash(new_question)
        raw_candidates.append({
            "id": int(row.get("id")),
            "source_quiz_title": row.get("source_quiz_title") or "",
            "domain": row.get("domain") or "",
            "subdomain": row.get("subdomain") or "",
            "question_preview": audit_row.get("question_preview") or "",
            "current_db_type": db_type,
            "current_json_type": old_json_type,
            "target_type": detected_type,
            "issues": audit_row.get("issues") or [],
            "current_hash": str(row.get("question_hash") or ""),
            "new_hash": new_hash,
            "_previous_question_json": question,
            "_new_question_json": new_question,
        })

    new_hash_counts: Dict[str, int] = {}
    for candidate in raw_candidates:
        new_hash = candidate["new_hash"]
        new_hash_counts[new_hash] = new_hash_counts.get(new_hash, 0) + 1

    applicable: List[Dict[str, Any]] = []
    blocked: List[Dict[str, Any]] = []
    for candidate in raw_candidates:
        owner = existing_hash_owner.get(candidate["new_hash"])
        block_reason = ""
        if owner is not None and owner != candidate["id"]:
            block_reason = f"hash_conflict_with_question_{owner}"
        elif new_hash_counts.get(candidate["new_hash"], 0) > 1:
            block_reason = "duplicate_target_hash_in_migration"

        public_candidate = {
            key: value
            for key, value in candidate.items()
            if not key.startswith("_")
        }
        if block_reason:
            public_candidate["blocked_reason"] = block_reason
            blocked.append(public_candidate)
        else:
            applicable.append(candidate)

    public_applicable = [
        {
            key: value
            for key, value in candidate.items()
            if not key.startswith("_")
        }
        for candidate in applicable
    ]

    return {
        "scope": "CDPO actif - banque uniquement",
        "candidate_count": len(public_applicable),
        "blocked_count": len(blocked),
        "candidates": public_applicable,
        "blocked": blocked,
    }


def _ensure_question_schema_migration_log(conn: Any) -> None:
    if _pg():
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS question_schema_migration_log (
                    id bigserial PRIMARY KEY,
                    migration_run_id text NOT NULL,
                    question_id bigint NOT NULL,
                    applied_at timestamptz NOT NULL DEFAULT now(),
                    previous_question_type text,
                    new_question_type text,
                    previous_question_hash text,
                    new_question_hash text,
                    previous_question_json jsonb NOT NULL,
                    new_question_json jsonb NOT NULL,
                    UNIQUE (migration_run_id, question_id)
                )
            """)
        return

    conn.execute("""
        CREATE TABLE IF NOT EXISTS question_schema_migration_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            migration_run_id TEXT NOT NULL,
            question_id INTEGER NOT NULL,
            applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            previous_question_type TEXT,
            new_question_type TEXT,
            previous_question_hash TEXT,
            new_question_hash TEXT,
            previous_question_json TEXT NOT NULL,
            new_question_json TEXT NOT NULL,
            UNIQUE (migration_run_id, question_id)
        )
    """)


def apply_safe_cdpo_question_migration(
    question_ids: List[int],
) -> Dict[str, Any]:
    """Applique une migration atomique des candidats sûrs CDPO.

    Un journal complet avant/après est créé dans question_schema_migration_log
    avant toute modification. Si une question n'est plus éligible au moment
    du clic, l'opération entière est annulée.
    """
    import uuid
    from datetime import datetime, timezone

    requested_ids = sorted({int(value) for value in question_ids})
    if not requested_ids:
        return {
            "applied": 0,
            "migration_run_id": "",
            "question_ids": [],
        }

    fresh_preview = build_safe_cdpo_migration_preview(limit=5000)
    candidates_by_id: Dict[int, Dict[str, Any]] = {}

    # Reconstitue les objets complets après la prévisualisation publique.
    records = {
        int(row.get("id")): row
        for row in list_question_bank_records_for_audit(
            include_inactive=False,
            limit=5000,
        )
        if row.get("id") is not None
    }

    for public_candidate in fresh_preview.get("candidates") or []:
        qid = int(public_candidate["id"])
        row = records.get(qid)
        if not row:
            continue

        audit_row = _build_schema_audit_row_for_bank_record(row)
        question = dict(row.get("question_json") or {})
        new_question = dict(question)
        new_question.update(dict(audit_row.get("suggested_patch") or {}))
        new_question["type"] = str(audit_row.get("detected_type") or "")
        new_question["schema_version"] = 2

        candidates_by_id[qid] = {
            "id": qid,
            "previous_question_type": str(row.get("question_type") or ""),
            "new_question_type": str(audit_row.get("detected_type") or ""),
            "previous_question_hash": str(row.get("question_hash") or ""),
            "new_question_hash": make_question_hash(new_question),
            "previous_question_json": question,
            "new_question_json": new_question,
        }

    missing = [
        qid for qid in requested_ids
        if qid not in candidates_by_id
    ]
    if missing:
        raise ValueError(
            "Migration annulée : certaines questions ne sont plus "
            f"éligibles à la migration sûre : {missing}"
        )

    migration_run_id = (
        "schema-v2-"
        + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        + "-"
        + uuid.uuid4().hex[:8]
    )

    with get_connection() as conn:
        try:
            _ensure_question_schema_migration_log(conn)

            if _pg():
                with conn.cursor() as cur:
                    for qid in requested_ids:
                        candidate = candidates_by_id[qid]
                        cur.execute(
                            """
                            SELECT
                                question_type,
                                question_hash,
                                question_json,
                                is_active,
                                training_scope
                            FROM question_bank
                            WHERE id = %s
                            FOR UPDATE
                            """,
                            (qid,),
                        )
                        current = cur.fetchone()
                        if not current:
                            raise ValueError(
                                f"Question {qid} introuvable pendant la migration."
                            )
                        current = _row(current)
                        if not bool(current.get("is_active")):
                            raise ValueError(
                                f"Question {qid} n'est plus active."
                            )
                        if str(current.get("training_scope") or "").strip().upper() != "CDPO":
                            raise ValueError(
                                f"Question {qid} n'appartient plus au périmètre CDPO."
                            )
                        if str(current.get("question_hash") or "") != candidate["previous_question_hash"]:
                            raise ValueError(
                                f"Question {qid} a changé depuis la prévisualisation."
                            )

                        cur.execute(
                            """
                            INSERT INTO question_schema_migration_log (
                                migration_run_id,
                                question_id,
                                previous_question_type,
                                new_question_type,
                                previous_question_hash,
                                new_question_hash,
                                previous_question_json,
                                new_question_json
                            )
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                            """,
                            (
                                migration_run_id,
                                qid,
                                candidate["previous_question_type"],
                                candidate["new_question_type"],
                                candidate["previous_question_hash"],
                                candidate["new_question_hash"],
                                _json_db(candidate["previous_question_json"]),
                                _json_db(candidate["new_question_json"]),
                            ),
                        )
                        cur.execute(
                            """
                            UPDATE question_bank
                            SET
                                question_type = %s,
                                question_hash = %s,
                                question_json = %s
                            WHERE id = %s
                            """,
                            (
                                candidate["new_question_type"],
                                candidate["new_question_hash"],
                                _json_db(candidate["new_question_json"]),
                                qid,
                            ),
                        )
            else:
                for qid in requested_ids:
                    candidate = candidates_by_id[qid]
                    current = conn.execute(
                        """
                        SELECT
                            question_type,
                            question_hash,
                            question_json,
                            is_active,
                            training_scope
                        FROM question_bank
                        WHERE id = ?
                        """,
                        (qid,),
                    ).fetchone()
                    if not current:
                        raise ValueError(
                            f"Question {qid} introuvable pendant la migration."
                        )
                    current = _row(current)
                    if not bool(current.get("is_active")):
                        raise ValueError(
                            f"Question {qid} n'est plus active."
                        )
                    if str(current.get("training_scope") or "").strip().upper() != "CDPO":
                        raise ValueError(
                            f"Question {qid} n'appartient plus au périmètre CDPO."
                        )
                    if str(current.get("question_hash") or "") != candidate["previous_question_hash"]:
                        raise ValueError(
                            f"Question {qid} a changé depuis la prévisualisation."
                        )

                    conn.execute(
                        """
                        INSERT INTO question_schema_migration_log (
                            migration_run_id,
                            question_id,
                            previous_question_type,
                            new_question_type,
                            previous_question_hash,
                            new_question_hash,
                            previous_question_json,
                            new_question_json
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            migration_run_id,
                            qid,
                            candidate["previous_question_type"],
                            candidate["new_question_type"],
                            candidate["previous_question_hash"],
                            candidate["new_question_hash"],
                            _json_db(candidate["previous_question_json"]),
                            _json_db(candidate["new_question_json"]),
                        ),
                    )
                    conn.execute(
                        """
                        UPDATE question_bank
                        SET
                            question_type = ?,
                            question_hash = ?,
                            question_json = ?
                        WHERE id = ?
                        """,
                        (
                            candidate["new_question_type"],
                            candidate["new_question_hash"],
                            _json_db(candidate["new_question_json"]),
                            qid,
                        ),
                    )

            conn.commit()
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise

    return {
        "applied": len(requested_ids),
        "migration_run_id": migration_run_id,
        "question_ids": requested_ids,
    }


def list_question_schema_migration_log(
    migration_run_id: str = "",
    limit: int = 500,
) -> List[Dict[str, Any]]:
    """Retourne le journal des sauvegardes de migration."""
    placeholder = "%s" if _pg() else "?"
    params: List[Any] = []
    where = ""
    if migration_run_id:
        where = f"WHERE migration_run_id = {placeholder}"
        params.append(migration_run_id)
    params.append(int(limit))

    try:
        rows = _fetchall(
            f"""
            SELECT
                migration_run_id,
                question_id,
                applied_at,
                previous_question_type,
                new_question_type,
                previous_question_hash,
                new_question_hash
            FROM question_schema_migration_log
            {where}
            ORDER BY id DESC
            LIMIT {placeholder}
            """,
            tuple(params),
        )
    except Exception:
        return []

    return rows


def build_cdpo_completion_preview(limit: int = 5000) -> Dict[str, Any]:
    """Retourne les questions orange de la banque CDPO active, sans modification."""
    records = list_question_bank_records_for_audit(
        include_inactive=False,
        limit=limit,
    )
    candidates: List[Dict[str, Any]] = []

    for row in records:
        if not bool(row.get("is_active")):
            continue
        if str(row.get("training_scope") or "").strip().upper() != "CDPO":
            continue

        audit_row = _build_schema_audit_row_for_bank_record(row)
        if audit_row.get("audit_action") != "needs_completion":
            continue

        question = dict(row.get("question_json") or {})
        candidates.append({
            "id": int(row.get("id")),
            "source_quiz_title": row.get("source_quiz_title") or "",
            "domain": row.get("domain") or "",
            "subdomain": row.get("subdomain") or "",
            "current_db_type": str(row.get("question_type") or ""),
            "current_json_type": str(question.get("type") or ""),
            "target_type": str(audit_row.get("detected_type") or ""),
            "issues": list(audit_row.get("issues") or []),
            "question_preview": audit_row.get("question_preview") or "",
            "suggested_patch": dict(audit_row.get("suggested_patch") or {}),
            "question": question,
        })

    return {
        "scope": "CDPO actif - banque uniquement",
        "candidate_count": len(candidates),
        "candidates": candidates,
    }


def _normalize_completion_patch(
    target_type: str,
    patch: Dict[str, Any],
) -> Dict[str, Any]:
    """Nettoie les champs saisis dans l'éditeur orange avant validation."""
    cleaned = dict(patch or {})

    if target_type == "point_allocation":
        try:
            total_points = int(cleaned.get("total_points") or 0)
        except Exception:
            total_points = 0
        if total_points <= 0:
            raise ValueError("Le total de points doit être un entier strictement positif.")
        cleaned["total_points"] = total_points
        cleaned["require_justification"] = bool(
            cleaned.get("require_justification", True)
        )

    elif target_type == "priority_ranking":
        ranking_mode = str(cleaned.get("ranking_mode") or "").strip()
        if ranking_mode not in {"rank_all", "top_n"}:
            raise ValueError(
                "Choisis un mode de classement : rank_all ou top_n."
            )
        cleaned["ranking_mode"] = ranking_mode
        if ranking_mode == "top_n":
            try:
                top_n = int(cleaned.get("top_n") or 0)
            except Exception:
                top_n = 0
            if top_n <= 0:
                raise ValueError("Le nombre d'éléments du top doit être positif.")
            cleaned["top_n"] = top_n
        else:
            cleaned.pop("top_n", None)
        cleaned["require_justification"] = bool(
            cleaned.get("require_justification", True)
        )

    elif target_type == "long_answer":
        criteria = cleaned.get("evaluation_criteria") or []
        if isinstance(criteria, str):
            criteria = [
                line.strip()
                for line in criteria.splitlines()
                if line.strip()
            ]
        if not isinstance(criteria, list) or not criteria:
            raise ValueError(
                "Ajoute au moins un critère d'évaluation pour la réponse rédigée."
            )
        cleaned["evaluation_criteria"] = [
            str(item).strip() for item in criteria if str(item).strip()
        ]
        if cleaned.get("max_points") not in (None, ""):
            try:
                max_points = float(cleaned["max_points"])
            except Exception:
                raise ValueError("Le barème maximal doit être numérique.")
            if max_points <= 0:
                raise ValueError("Le barème maximal doit être positif.")
            cleaned["max_points"] = max_points
        else:
            cleaned.pop("max_points", None)

    elif target_type == "fill_blank":
        answers = cleaned.get("correct_answers") or []
        if isinstance(answers, str):
            answers = [
                line.strip()
                for line in answers.splitlines()
                if line.strip()
            ]
        if not isinstance(answers, list) or not answers:
            raise ValueError(
                "Renseigne les réponses attendues, une réponse par trou."
            )
        cleaned["correct_answers"] = [
            str(item).strip() for item in answers if str(item).strip()
        ]

    elif target_type == "ordering":
        order = cleaned.get("correct_order") or []
        if isinstance(order, str):
            compact = "".join(ch for ch in order.upper() if ch.isalpha())
            order = list(compact)
        if not isinstance(order, list) or not order:
            raise ValueError("Renseigne l'ordre attendu, par exemple ABCDE.")
        cleaned["correct_order"] = [
            str(item).strip().upper()
            for item in order
            if str(item).strip()
        ]

    elif target_type == "matching":
        pairs = cleaned.get("pairs") or []
        if not isinstance(pairs, list) or not pairs:
            raise ValueError("Renseigne au moins une paire d'appariement.")
        normalized_pairs = []
        for pair in pairs:
            if not isinstance(pair, dict):
                continue
            left = str(pair.get("left") or "").strip()
            right = str(pair.get("right") or "").strip()
            if left and right:
                normalized_pairs.append({"left": left, "right": right})
        if not normalized_pairs:
            raise ValueError("Les paires d'appariement sont incomplètes.")
        cleaned["pairs"] = normalized_pairs

    elif target_type == "short_answer":
        accepted = cleaned.get("accepted_answers") or []
        if isinstance(accepted, str):
            accepted = [
                part.strip()
                for part in __import__("re").split(r"[|;\n]", accepted)
                if part.strip()
            ]
        cleaned["accepted_answers"] = list(accepted) if isinstance(accepted, list) else []
        max_words = cleaned.get("max_words")
        if max_words not in (None, ""):
            try:
                max_words = int(max_words)
            except Exception:
                raise ValueError("Le nombre maximal de mots doit être un entier.")
            if max_words <= 0:
                raise ValueError("Le nombre maximal de mots doit être positif.")
            cleaned["max_words"] = max_words
        else:
            cleaned.pop("max_words", None)

    elif target_type == "self_assessment":
        cleaned["scale_min"] = int(cleaned.get("scale_min") or 1)
        cleaned["scale_max"] = int(cleaned.get("scale_max") or 5)
        if cleaned["scale_min"] >= cleaned["scale_max"]:
            raise ValueError("L'échelle d'auto-positionnement est invalide.")

    elif target_type in {"single_choice", "true_false"}:
        options = cleaned.get("options")
        if isinstance(options, str):
            options = [
                line.strip()
                for line in options.splitlines()
                if line.strip()
            ]
        if options is not None:
            cleaned["options"] = list(options)
        if cleaned.get("correct_answer") in (None, ""):
            raise ValueError("Renseigne la bonne réponse.")

    return cleaned


def apply_cdpo_completion_patch(
    question_id: int,
    completion_patch: Dict[str, Any],
) -> Dict[str, Any]:
    """Complète une question orange CDPO avec sauvegarde avant/après atomique."""
    import uuid
    from datetime import datetime, timezone
    from utils.question_schema import audit_action, classify_question

    qid = int(question_id)
    records = {
        int(row.get("id")): row
        for row in list_question_bank_records_for_audit(
            include_inactive=False,
            limit=5000,
        )
        if row.get("id") is not None
    }
    row = records.get(qid)
    if not row:
        raise ValueError(f"Question {qid} introuvable.")
    if not bool(row.get("is_active")):
        raise ValueError(f"Question {qid} n'est plus active.")
    if str(row.get("training_scope") or "").strip().upper() != "CDPO":
        raise ValueError(f"Question {qid} n'appartient pas au périmètre CDPO.")

    audit_row = _build_schema_audit_row_for_bank_record(row)
    if audit_row.get("audit_action") != "needs_completion":
        raise ValueError(
            f"Question {qid} n'est plus classée orange au moment de la validation."
        )

    completion_patch = dict(completion_patch or {})
    requested_type = str(
        completion_patch.pop("_target_type_override", "") or ""
    ).strip()
    detected_type = str(audit_row.get("detected_type") or "")
    allowed_types = {
        "single_choice",
        "true_false",
        "matching",
        "ordering",
        "fill_blank",
        "self_assessment",
        "point_allocation",
        "priority_ranking",
        "short_answer",
        "long_answer",
    }
    if requested_type and requested_type not in allowed_types:
        raise ValueError(f"Type de question non autorisé : {requested_type}")

    target_type = requested_type or detected_type
    cleaned_patch = _normalize_completion_patch(target_type, completion_patch)

    previous_question = dict(row.get("question_json") or {})
    new_question = dict(previous_question)
    new_question.update(dict(audit_row.get("suggested_patch") or {}))
    new_question.update(cleaned_patch)
    new_question["type"] = target_type
    new_question["schema_version"] = 2
    new_question["schema_type_locked"] = True
    new_question["schema_type_source"] = "trainer_review"

    # Nettoie les champs incompatibles lorsqu'un formateur remplace le type proposé.
    if target_type != "point_allocation":
        new_question.pop("total_points", None)
    if target_type != "priority_ranking":
        new_question.pop("ranking_mode", None)
        new_question.pop("top_n", None)
    if target_type not in {"point_allocation", "priority_ranking"}:
        new_question.pop("require_justification", None)
    if target_type in {"short_answer", "long_answer"}:
        new_question.pop("items", None)

    # Validations de cohérence propres aux types structurés.
    if target_type == "priority_ranking":
        item_count = len(new_question.get("items") or [])
        if new_question.get("ranking_mode") == "top_n":
            top_n = int(new_question.get("top_n") or 0)
            if item_count and top_n > item_count:
                raise ValueError(
                    f"Le top {top_n} dépasse les {item_count} éléments disponibles."
                )

    if target_type == "fill_blank":
        text = str(new_question.get("question") or "")
        blank_count = len(
            __import__("re").findall(
                r"\[\s*(?:\.\.\.|…+)\s*\]",
                text,
            )
        )
        answers = new_question.get("correct_answers") or []
        if blank_count and len(answers) != blank_count:
            raise ValueError(
                f"Cette question contient {blank_count} trou(s) mais "
                f"{len(answers)} réponse(s) ont été renseignée(s)."
            )

    validation = classify_question(new_question)
    validation_row = {
        "detected_type": validation.get("detected_type"),
        "confidence": validation.get("confidence"),
        "issues": validation.get("issues") or [],
    }
    if audit_action(validation_row) == "needs_completion":
        raise ValueError(
            "La question reste incomplète après validation : "
            + ", ".join(validation.get("issues") or [])
        )
    if validation.get("detected_type") == "unknown":
        raise ValueError(
            "La question devient ambiguë après la modification ; migration annulée."
        )

    previous_hash = str(row.get("question_hash") or "")
    new_hash = make_question_hash(new_question)

    conflict_rows = _fetchall(
        "SELECT id FROM question_bank WHERE question_hash = "
        + ("%s" if _pg() else "?"),
        (new_hash,),
    )
    for conflict in conflict_rows:
        owner = int(conflict.get("id"))
        if owner != qid:
            raise ValueError(
                f"Une autre question ({owner}) possède déjà la même empreinte."
            )

    migration_run_id = (
        "schema-v2-orange-"
        + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        + "-"
        + uuid.uuid4().hex[:8]
    )

    with get_connection() as conn:
        try:
            _ensure_question_schema_migration_log(conn)
            if _pg():
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT question_hash, is_active, training_scope
                        FROM question_bank
                        WHERE id = %s
                        FOR UPDATE
                        """,
                        (qid,),
                    )
                    current = cur.fetchone()
                    if not current:
                        raise ValueError(f"Question {qid} introuvable.")
                    current = _row(current)
                    if str(current.get("question_hash") or "") != previous_hash:
                        raise ValueError(
                            "La question a changé depuis son affichage. "
                            "Recharge l'audit avant de recommencer."
                        )

                    cur.execute(
                        """
                        INSERT INTO question_schema_migration_log (
                            migration_run_id,
                            question_id,
                            previous_question_type,
                            new_question_type,
                            previous_question_hash,
                            new_question_hash,
                            previous_question_json,
                            new_question_json
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            migration_run_id,
                            qid,
                            str(row.get("question_type") or ""),
                            target_type,
                            previous_hash,
                            new_hash,
                            _json_db(previous_question),
                            _json_db(new_question),
                        ),
                    )
                    cur.execute(
                        """
                        UPDATE question_bank
                        SET question_type = %s, question_hash = %s, question_json = %s
                        WHERE id = %s
                        """,
                        (
                            target_type,
                            new_hash,
                            _json_db(new_question),
                            qid,
                        ),
                    )
            else:
                current = conn.execute(
                    """
                    SELECT question_hash, is_active, training_scope
                    FROM question_bank
                    WHERE id = ?
                    """,
                    (qid,),
                ).fetchone()
                if not current:
                    raise ValueError(f"Question {qid} introuvable.")
                current = _row(current)
                if str(current.get("question_hash") or "") != previous_hash:
                    raise ValueError(
                        "La question a changé depuis son affichage. "
                        "Recharge l'audit avant de recommencer."
                    )

                conn.execute(
                    """
                    INSERT INTO question_schema_migration_log (
                        migration_run_id,
                        question_id,
                        previous_question_type,
                        new_question_type,
                        previous_question_hash,
                        new_question_hash,
                        previous_question_json,
                        new_question_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        migration_run_id,
                        qid,
                        str(row.get("question_type") or ""),
                        target_type,
                        previous_hash,
                        new_hash,
                        _json_db(previous_question),
                        _json_db(new_question),
                    ),
                )
                conn.execute(
                    """
                    UPDATE question_bank
                    SET question_type = ?, question_hash = ?, question_json = ?
                    WHERE id = ?
                    """,
                    (
                        target_type,
                        new_hash,
                        _json_db(new_question),
                        qid,
                    ),
                )

            conn.commit()
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise

    return {
        "question_id": qid,
        "migration_run_id": migration_run_id,
        "target_type": target_type,
        "issues_before": list(audit_row.get("issues") or []),
        "issues_after": list(validation.get("issues") or []),
        "detected_type_before": detected_type,
        "trainer_override": bool(requested_type and requested_type != detected_type),
    }


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

