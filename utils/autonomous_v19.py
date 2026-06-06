from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

import streamlit as st

from utils.db_runtime import get_connection, get_database_mode
from utils.learner_db import finish_attempt, save_attempt_result, start_attempt
from utils.question_bank import build_quiz_from_bank, select_adaptive_questions


def _pg() -> bool:
    return get_database_mode() == "postgres"


def _param() -> str:
    return "%s" if _pg() else "?"


def _rowdict(row: Any) -> Dict[str, Any]:
    if isinstance(row, dict):
        return dict(row)
    return dict(row)


def _json_load(value: Any) -> Any:
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
                return [_rowdict(r) for r in cur.fetchall()]
        return [_rowdict(r) for r in conn.execute(sql, params).fetchall()]


@st.cache_data(ttl=120)
def _bank_meta() -> Dict[str, Any]:
    active = "true" if _pg() else "1"
    count_rows = _fetchall(f"SELECT COUNT(*) AS c FROM question_bank WHERE is_active = {active}")
    perimeter_rows = _fetchall(f"""
        SELECT DISTINCT COALESCE(NULLIF(source_quiz_title, ''), 'Tous les périmètres') AS label
        FROM question_bank
        WHERE is_active = {active}
        ORDER BY label ASC
    """)
    domain_rows = _fetchall(f"""
        SELECT DISTINCT COALESCE(NULLIF(domain, ''), 'Non classé') AS label
        FROM question_bank
        WHERE is_active = {active}
        ORDER BY label ASC
    """)
    difficulty_rows = _fetchall(f"""
        SELECT DISTINCT COALESCE(NULLIF(difficulty, ''), 'Non renseigné') AS label
        FROM question_bank
        WHERE is_active = {active}
        ORDER BY label ASC
    """)
    perimeters = [r["label"] for r in perimeter_rows if r.get("label")]
    domains = [r["label"] for r in domain_rows if r.get("label")]
    difficulties = [r["label"] for r in difficulty_rows if r.get("label")]
    return {
        "total": int(count_rows[0]["c"]) if count_rows else 0,
        "perimeters": ["Tous les périmètres"] + [p for p in perimeters if p != "Tous les périmètres"],
        "domains": ["Tous"] + domains,
        "difficulties": ["Tous"] + difficulties,
    }


def _select_questions(limit: int, perimeter: str, domain: str, difficulty: str) -> List[Dict[str, Any]]:
    active = "true" if _pg() else "1"
    q = _param()
    clauses = [f"is_active = {active}"]
    params: List[Any] = []

    if perimeter and perimeter != "Tous les périmètres":
        clauses.append(f"COALESCE(NULLIF(source_quiz_title, ''), 'Tous les périmètres') = {q}")
        params.append(perimeter)
    if domain and domain != "Tous":
        clauses.append(f"COALESCE(NULLIF(domain, ''), 'Non classé') = {q}")
        params.append(domain)
    if difficulty and difficulty != "Tous":
        clauses.append(f"COALESCE(NULLIF(difficulty, ''), 'Non renseigné') = {q}")
        params.append(difficulty)

    clauses_sql = " AND ".join(clauses)
    rows = _fetchall(
        f"SELECT id, question_json FROM question_bank WHERE {clauses_sql} ORDER BY RANDOM() LIMIT {q}",
        tuple(params + [int(limit)]),
    )

    questions = []
    for row in rows:
        item = _json_load(row.get("question_json")) or {}
        if isinstance(item, dict):
            item["_bank_id"] = row.get("id")
            questions.append(item)
    return questions


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _option_label(index: int) -> str:
    return chr(ord("A") + index)


def _feedbacks(question: Dict[str, Any]) -> Dict[str, str]:
    raw = question.get("feedbacks") or {}
    return {str(k): str(v) for k, v in raw.items()} if isinstance(raw, dict) else {}


def _correct_label(question: Dict[str, Any]) -> str:
    correct = str(question.get("correct_answer", "") or "").strip()
    options = question.get("options") or []
    if len(correct) == 1 and correct.upper() in [_option_label(i) for i in range(len(options))]:
        return correct.upper()
    for i, option in enumerate(options):
        if _norm(option) == _norm(correct):
            return _option_label(i)
    return correct


def evaluate_v19_answer(question: Dict[str, Any], user_answer: Any) -> Dict[str, Any]:
    qtype = question.get("type", "")
    explanation = str(question.get("explanation", "") or "")
    remediation = str(question.get("remediation", "") or question.get("piste_de_revision", "") or "")
    result = {
        "correct_answer": question.get("correct_answer", ""),
        "is_correct": None,
        "score": 0.0,
        "selected_feedback": "",
        "correct_feedback": explanation,
        "remediation": remediation,
    }

    if qtype == "matching":
        expected = {}
        for pair in question.get("pairs") or []:
            if isinstance(pair, dict) and pair.get("left"):
                expected[pair.get("left")] = pair.get("right", "")
        result["correct_answer"] = expected
        ok = bool(expected) and isinstance(user_answer, dict) and all(
            _norm(user_answer.get(left, "")) == _norm(right) for left, right in expected.items()
        )
        result["is_correct"] = ok
        result["score"] = 1.0 if ok else 0.0
        result["selected_feedback"] = "Associations correctes." if ok else "Certaines associations ne sont pas correctes."
        return result

    if qtype == "short_answer":
        result["correct_answer"] = question.get("correct_answer", "")
        result["is_correct"] = None
        result["selected_feedback"] = "Réponse enregistrée. Cette question nécessite une correction manuelle."
        return result

    selected = str(user_answer or "").strip().upper()
    correct = _correct_label(question)
    options = question.get("options") or []
    ok = _norm(selected) == _norm(correct)

    if len(selected) == 1 and selected.isalpha():
        idx = ord(selected) - ord("A")
        if 0 <= idx < len(options) and _norm(options[idx]) == _norm(question.get("correct_answer", "")):
            ok = True

    result["correct_answer"] = correct
    result["is_correct"] = ok
    result["score"] = 1.0 if ok else 0.0
    fb = _feedbacks(question)
    result["selected_feedback"] = fb.get(selected, "") or ("Bonne réponse." if ok else f"La réponse {selected} n’est pas la bonne réponse.")
    result["correct_feedback"] = explanation or f"La bonne réponse est : {correct}."
    return result


def _render_input(question: Dict[str, Any], idx: int, existing: Any = None) -> Any:
    qtype = question.get("type", "")
    options = question.get("options") or []
    prefix = f"v19_auto_form_q_{idx}"

    if qtype in ["single_choice", "true_false"] and options:
        display = [f"{_option_label(i)}. {option}" for i, option in enumerate(options)]
        default = None
        if isinstance(existing, str) and existing:
            for i, opt in enumerate(display):
                if opt.startswith(existing + "."):
                    default = i
                    break
        selected = st.radio("Choisis une réponse", display, index=default, key=f"{prefix}_radio")
        return selected.split(".", 1)[0].strip() if selected else ""

    if qtype == "matching":
        pairs = question.get("pairs") or []
        right_options = []
        for pair in pairs:
            if isinstance(pair, dict) and pair.get("right") not in right_options:
                right_options.append(pair.get("right"))
        current = existing if isinstance(existing, dict) else {}
        answer = {}
        for pair in pairs:
            left = pair.get("left", "") if isinstance(pair, dict) else ""
            if not left:
                continue
            values = [""] + right_options
            index = values.index(current.get(left, "")) if current.get(left, "") in values else 0
            answer[left] = st.selectbox(f"Associer : {left}", values, index=index, key=f"{prefix}_{left}")
        return answer

    return st.text_area("Ta réponse", value=existing if isinstance(existing, str) else "", height=120, key=f"{prefix}_text")


def _level(pct: float) -> str:
    if pct < 50:
        return "Debutant"
    if pct < 75:
        return "Intermediaire"
    return "Avance"


def _clear_state() -> None:
    for key in list(st.session_state.keys()):
        if str(key).startswith("v19_auto_") or str(key).startswith("v19_auto_form_"):
            del st.session_state[key]


def _finish(learner: Dict[str, Any]) -> None:
    quiz = st.session_state.get("v19_auto_quiz") or {}
    questions = quiz.get("questions", []) or []
    answers = st.session_state.get("v19_auto_answers") or {}

    attempt_id = start_attempt(int(learner["id"]), None, quiz.get("quiz_title", "Entraînement autonome"))

    score = 0.0
    max_score = 0.0
    manual = 0
    details = []

    for idx, question in enumerate(questions, start=1):
        user_answer = answers.get(str(idx))
        ev = evaluate_v19_answer(question, user_answer)
        if ev["is_correct"] is None:
            manual += 1
        else:
            max_score += 1
            score += float(ev["score"])

        save_attempt_result(
            attempt_id=attempt_id,
            question_index=idx,
            question=question,
            user_answer=user_answer,
            correct_answer=ev["correct_answer"],
            is_correct=ev["is_correct"],
            score=float(ev["score"]),
            selected_feedback=ev.get("selected_feedback", ""),
            correct_feedback=ev.get("correct_feedback", ""),
        )
        details.append({"index": idx, "question": question, "user_answer": user_answer, "evaluation": ev})

    pct = round((score / max_score) * 100, 1) if max_score else 0
    finish_attempt(attempt_id, score, max_score, pct, _level(pct), manual)

    st.session_state.v19_auto_submitted = True
    st.session_state.v19_auto_attempt_id = attempt_id
    st.session_state.v19_auto_result = {
        "score": score,
        "max_score": max_score,
        "percentage": pct,
        "recommended_level": _level(pct),
        "manual_count": manual,
        "details": details,
    }


def _render_result() -> None:
    result = st.session_state.get("v19_auto_result") or {}
    if not result:
        return
    st.markdown("### Résultat enregistré")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Score global", f"{result.get('percentage', 0)}%")
    c2.metric("Score", f"{result.get('score', 0)} / {result.get('max_score', 0)}")
    c3.metric("Niveau conseillé", result.get("recommended_level", "-"))
    c4.metric("À corriger", result.get("manual_count", 0))
    st.success(f"Tentative enregistrée. ID : {st.session_state.get('v19_auto_attempt_id')}")

    with st.expander("Voir le détail des réponses", expanded=False):
        for item in result.get("details", []):
            ev = item["evaluation"]
            status = "Correct" if ev["is_correct"] is True else "Incorrect" if ev["is_correct"] is False else "À corriger"
            st.markdown(f"#### Q{item['index']} — {status}")
            st.write(item["question"].get("question", ""))
            st.write("Réponse apprenant :")
            st.code(json.dumps(item["user_answer"], ensure_ascii=False, indent=2))
            st.write("Correction :")
            st.code(json.dumps(ev["correct_answer"], ensure_ascii=False, indent=2))
            if ev.get("selected_feedback"):
                st.warning(ev["selected_feedback"])
            if ev.get("correct_feedback"):
                st.info(ev["correct_feedback"])

    if st.button("Démarrer un nouvel entraînement", width="stretch", key="v19_auto_new"):
        _clear_state()
        st.rerun()


def _render_quiz(learner: Dict[str, Any]) -> None:
    quiz = st.session_state.get("v19_auto_quiz")
    if not quiz:
        return

    if st.session_state.get("v19_auto_submitted"):
        _render_result()
        return

    questions = quiz.get("questions", []) or []
    answers = st.session_state.setdefault("v19_auto_answers", {})
    current = max(1, min(int(st.session_state.get("v19_auto_current", 1)), len(questions)))
    st.session_state.v19_auto_current = current

    answered = len([v for v in answers.values() if v not in [None, "", {}]])
    st.progress(answered / len(questions))
    st.caption(f"Question {current} / {len(questions)} — {answered} réponse(s) enregistrée(s)")

    question = questions[current - 1]
    with st.form(f"v19_answer_form_{current}", clear_on_submit=False):
        st.markdown(f"#### Question {current}")
        st.write(question.get("question", ""))
        answer = _render_input(question, current, answers.get(str(current)))
        cols = st.columns(3)
        save = cols[0].form_submit_button("Enregistrer cette réponse", type="primary", width="stretch")
        prev_btn = cols[1].form_submit_button("Question précédente", width="stretch", disabled=current <= 1)
        next_btn = cols[2].form_submit_button("Question suivante", width="stretch", disabled=current >= len(questions))

    if save:
        answers[str(current)] = answer
        st.session_state.v19_auto_answers = answers
        st.success("Réponse enregistrée.")
    if prev_btn:
        answers[str(current)] = answer
        st.session_state.v19_auto_answers = answers
        st.session_state.v19_auto_current = current - 1
        st.rerun()
    if next_btn:
        answers[str(current)] = answer
        st.session_state.v19_auto_answers = answers
        st.session_state.v19_auto_current = current + 1
        st.rerun()

    missing = [str(i) for i in range(1, len(questions) + 1) if answers.get(str(i)) in [None, "", {}]]
    if missing:
        st.info(f"Questions sans réponse enregistrée : {', '.join(missing[:15])}" + ("..." if len(missing) > 15 else ""))

    with st.form("v19_finish_form", clear_on_submit=False):
        finish = st.form_submit_button("Terminer et enregistrer mes résultats", type="primary", width="stretch", disabled=bool(missing))
    if finish:
        _finish(learner)
        st.rerun()

    if st.button("Abandonner cet entraînement", width="stretch", key="v19_cancel"):
        _clear_state()
        st.rerun()


def render_v19_autonomous_mode(learner: Optional[Dict[str, Any]]) -> None:
    if not learner:
        return

    with st.expander("Entraînement / examen autonome", expanded=True):
        st.caption("Le mode autonome pioche dans la banque de questions et enregistre les résultats dans l’historique apprenant.")

        meta = _bank_meta()
        total = int(meta["total"])
        if total <= 0:
            st.warning("La banque de questions est vide dans la base active.")
            return

        st.info("Choisis le périmètre, le mode et le tirage. Le quiz ne démarre que lorsque tu appuies sur Démarrer.")

        with st.form("v19_start_form", clear_on_submit=False):
            c1, c2, c3 = st.columns(3)
            perimeter = c1.selectbox("Périmètre / formation", meta["perimeters"], key="v19_auto_perimeter")
            mode = c2.selectbox("Mode", ["Entraînement libre", "Examen blanc autonome"], key="v19_auto_type")
            selection = c3.selectbox("Tirage", ["Aléatoire", "Adaptatif selon mes erreurs"], key="v19_auto_selection_mode")

            c4, c5, c6 = st.columns(3)
            count = c4.number_input("Nombre de questions", min_value=1, max_value=max(1, min(80, total)), value=min(10, total), step=1, key="v19_auto_count")
            domain = c5.selectbox("Domaine", meta["domains"], key="v19_auto_domain")
            difficulty = c6.selectbox("Niveau", meta["difficulties"], key="v19_auto_difficulty")
            st.caption("Entraînement libre : format souple. Examen blanc autonome : format cadré, utile pour simuler une épreuve.")
            start = st.form_submit_button("Démarrer", type="primary", width="stretch")

        if start:
            if selection.startswith("Adaptatif") and perimeter == "Tous les périmètres":
                questions = select_adaptive_questions(
                    learner_email=learner.get("email", ""),
                    limit=int(count),
                    domain="" if domain == "Tous" else domain,
                    difficulty="" if difficulty == "Tous" else difficulty,
                )
            else:
                questions = _select_questions(
                    limit=int(count),
                    perimeter=perimeter,
                    domain=domain,
                    difficulty=difficulty,
                )

            if not questions:
                st.warning("Aucune question trouvée avec ces critères.")
            else:
                clean = []
                for q in questions:
                    item = dict(q)
                    item.pop("_bank_id", None)
                    clean.append(item)
                quiz = build_quiz_from_bank(
                    questions=clean,
                    title=f"{mode} — {perimeter} — {len(clean)} questions",
                    mode=selection,
                    learner_email=learner.get("email", ""),
                )
                st.session_state.v19_auto_quiz = quiz
                st.session_state.v19_auto_answers = {}
                st.session_state.v19_auto_current = 1
                st.session_state.v19_auto_submitted = False
                st.session_state.v19_auto_result = {}
                st.session_state.v19_auto_attempt_id = None
                st.success("Quiz démarré.")
                st.rerun()

        _render_quiz(learner)
