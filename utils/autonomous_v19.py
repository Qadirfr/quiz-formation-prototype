from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional

import streamlit as st

from utils.learner_db import finish_attempt, save_attempt_result, start_attempt
from utils.question_bank import (
    build_quiz_from_bank,
    get_question_bank_stats,
    list_bank_difficulties,
    list_bank_domains,
    select_adaptive_questions,
    select_random_questions,
)


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
        result["score"] = 0.0
        result["selected_feedback"] = "Réponse enregistrée. Cette question nécessite une correction manuelle."
        return result

    selected_label = str(user_answer or "").strip().upper()
    correct_label = _correct_label(question)
    options = question.get("options") or []

    ok = _norm(selected_label) == _norm(correct_label)
    if len(selected_label) == 1 and selected_label.isalpha():
        idx = ord(selected_label) - ord("A")
        if 0 <= idx < len(options) and _norm(options[idx]) == _norm(question.get("correct_answer", "")):
            ok = True

    result["correct_answer"] = correct_label
    result["is_correct"] = ok
    result["score"] = 1.0 if ok else 0.0

    fb = _feedbacks(question)
    result["selected_feedback"] = fb.get(selected_label, "") or (
        "Bonne réponse." if ok else f"La réponse {selected_label} n’est pas la bonne réponse."
    )
    result["correct_feedback"] = explanation or f"La bonne réponse est : {correct_label}."
    return result


def _render_question_input(question: Dict[str, Any], idx: int, existing: Any = None) -> Any:
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

        selected = st.radio(
            "Choisis une réponse",
            display,
            index=default,
            key=f"{prefix}_radio",
        )
        if selected:
            return selected.split(".", 1)[0].strip()
        return ""

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
            current_value = current.get(left, "")
            index = values.index(current_value) if current_value in values else 0
            answer[left] = st.selectbox(
                f"Associer : {left}",
                values,
                index=index,
                key=f"{prefix}_match_{left}",
            )
        return answer

    return st.text_area(
        "Ta réponse",
        value=existing if isinstance(existing, str) else "",
        height=120,
        key=f"{prefix}_text",
    )


def _recommend_level(percentage: float) -> str:
    if percentage < 50:
        return "Debutant"
    if percentage < 75:
        return "Intermediaire"
    return "Avance"


def _clear_v19_state() -> None:
    for key in list(st.session_state.keys()):
        if str(key).startswith("v19_auto_") or str(key).startswith("v19_auto_form_"):
            del st.session_state[key]


def _finish_and_save(learner: Dict[str, Any], quiz: Dict[str, Any], answers: Dict[str, Any]) -> None:
    questions = quiz.get("questions", []) or []

    attempt_id = start_attempt(
        learner_id=int(learner["id"]),
        quiz_id=None,
        quiz_title=quiz.get("quiz_title", "Entraînement autonome depuis la banque"),
    )

    score = 0.0
    max_score = 0.0
    manual_count = 0
    details = []

    for idx, question in enumerate(questions, start=1):
        user_answer = answers.get(str(idx))
        evaluation = evaluate_v19_answer(question, user_answer)

        if evaluation["is_correct"] is None:
            manual_count += 1
        else:
            max_score += 1.0
            score += float(evaluation["score"])

        save_attempt_result(
            attempt_id=attempt_id,
            question_index=idx,
            question=question,
            user_answer=user_answer,
            correct_answer=evaluation["correct_answer"],
            is_correct=evaluation["is_correct"],
            score=float(evaluation["score"]),
            selected_feedback=evaluation.get("selected_feedback", ""),
            correct_feedback=evaluation.get("correct_feedback", ""),
        )

        details.append(
            {
                "index": idx,
                "question": question,
                "user_answer": user_answer,
                "evaluation": evaluation,
            }
        )

    percentage = round((score / max_score) * 100, 1) if max_score else 0.0
    recommended = _recommend_level(percentage)

    finish_attempt(
        attempt_id=attempt_id,
        score=score,
        max_score=max_score,
        percentage=percentage,
        recommended_level=recommended,
        manual_count=manual_count,
    )

    st.session_state.v19_auto_submitted = True
    st.session_state.v19_auto_attempt_id = attempt_id
    st.session_state.v19_auto_result = {
        "score": score,
        "max_score": max_score,
        "percentage": percentage,
        "recommended_level": recommended,
        "manual_count": manual_count,
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

    attempt_id = st.session_state.get("v19_auto_attempt_id")
    if attempt_id:
        st.success(f"Tentative enregistrée dans l’historique apprenant. ID : {attempt_id}")

    with st.expander("Voir le détail des réponses", expanded=False):
        for item in result.get("details", []):
            question = item["question"]
            evaluation = item["evaluation"]
            idx = item["index"]
            status = "Correct" if evaluation["is_correct"] is True else "Incorrect" if evaluation["is_correct"] is False else "À corriger"

            st.markdown(f"#### Q{idx} — {status}")
            st.write(question.get("question", ""))

            st.write("Réponse apprenant :")
            st.code(json.dumps(item["user_answer"], ensure_ascii=False, indent=2))

            st.write("Correction :")
            st.code(json.dumps(evaluation["correct_answer"], ensure_ascii=False, indent=2))

            if evaluation.get("selected_feedback"):
                st.warning(evaluation["selected_feedback"])
            if evaluation.get("correct_feedback"):
                st.info(evaluation["correct_feedback"])
            if evaluation.get("remediation"):
                st.caption(f"Piste de travail : {evaluation['remediation']}")

    if st.button("Démarrer un nouvel entraînement", width="stretch", key="v19_auto_new"):
        _clear_v19_state()
        st.rerun()


def _render_active_quiz(learner: Dict[str, Any]) -> None:
    quiz = st.session_state.get("v19_auto_quiz")
    if not quiz:
        return

    questions = quiz.get("questions", []) or []
    if not questions:
        st.warning("Aucune question dans ce quiz.")
        return

    if st.session_state.get("v19_auto_submitted"):
        _render_result()
        return

    st.markdown("### Passation autonome V19")
    st.caption("Les choix ne relancent plus toute la page. Le traitement se fait uniquement quand tu valides le formulaire.")

    answers = st.session_state.setdefault("v19_auto_answers", {})
    current = int(st.session_state.get("v19_auto_current", 1))
    current = max(1, min(current, len(questions)))
    st.session_state.v19_auto_current = current

    answered_count = len([k for k, v in answers.items() if v not in [None, "", {}]])
    st.progress(answered_count / len(questions))
    st.caption(f"Question {current} / {len(questions)} — {answered_count} réponse(s) enregistrée(s)")

    question = questions[current - 1]

    with st.form(key=f"v19_answer_form_{current}", clear_on_submit=False):
        st.markdown(f"#### Question {current}")
        st.write(question.get("question", ""))

        existing = answers.get(str(current))
        user_answer = _render_question_input(question, current, existing=existing)

        cols = st.columns(3)
        save_clicked = cols[0].form_submit_button("Enregistrer cette réponse", type="primary", width="stretch")
        prev_clicked = cols[1].form_submit_button("Question précédente", width="stretch", disabled=current <= 1)
        next_clicked = cols[2].form_submit_button("Question suivante", width="stretch", disabled=current >= len(questions))

    if save_clicked:
        answers[str(current)] = user_answer
        st.session_state.v19_auto_answers = answers
        st.success("Réponse enregistrée.")

    if prev_clicked:
        answers[str(current)] = user_answer
        st.session_state.v19_auto_answers = answers
        st.session_state.v19_auto_current = current - 1
        st.rerun()

    if next_clicked:
        answers[str(current)] = user_answer
        st.session_state.v19_auto_answers = answers
        st.session_state.v19_auto_current = current + 1
        st.rerun()

    unanswered = [str(i) for i in range(1, len(questions) + 1) if str(i) not in answers or answers.get(str(i)) in [None, "", {}]]
    if unanswered:
        st.info(f"Questions sans réponse enregistrée : {', '.join(unanswered[:15])}" + ("..." if len(unanswered) > 15 else ""))

    with st.form(key="v19_finish_form", clear_on_submit=False):
        finish_clicked = st.form_submit_button(
            "Terminer et enregistrer mes résultats",
            type="primary",
            width="stretch",
            disabled=bool(unanswered),
        )

    if finish_clicked:
        _finish_and_save(learner, quiz, answers)
        st.rerun()

    if st.button("Abandonner cet entraînement", width="stretch", key="v19_cancel"):
        _clear_v19_state()
        st.rerun()


def render_v19_autonomous_mode(learner: Optional[Dict[str, Any]]) -> None:
    if not learner:
        return

    with st.expander("Mode autonome fiable V19 — depuis la banque de questions", expanded=True):
        st.caption(
            "Ce mode pioche dans la banque, affiche les questions une par une, "
            "puis enregistre les résultats dans l’historique apprenant."
        )

        stats = get_question_bank_stats()
        total = int(stats.get("total", 0) or 0)

        if total <= 0:
            st.warning("La banque de questions est vide dans la base active.")
            return

        domains = ["Tous"] + list_bank_domains()
        difficulties = ["Tous"] + list_bank_difficulties()

        with st.form("v19_start_form", clear_on_submit=False):
            col1, col2, col3, col4 = st.columns(4)

            with col1:
                training_type = st.selectbox("Type", ["Entraînement libre", "Examen autonome"], key="v19_auto_type")
            with col2:
                selection_mode = st.selectbox("Sélection", ["Aléatoire", "Adaptatif selon mes erreurs"], key="v19_auto_selection_mode")
            with col3:
                count = st.number_input(
                    "Nombre de questions",
                    min_value=1,
                    max_value=max(1, min(80, total)),
                    value=min(10, total),
                    step=1,
                    key="v19_auto_count",
                )
            with col4:
                domain = st.selectbox("Domaine", domains, key="v19_auto_domain")

            difficulty = st.selectbox("Niveau", difficulties, key="v19_auto_difficulty")

            start_clicked = st.form_submit_button("Démarrer un nouveau quiz autonome V19", type="primary", width="stretch")

        if start_clicked:
            if selection_mode.startswith("Adaptatif"):
                questions = select_adaptive_questions(
                    learner_email=learner.get("email", ""),
                    limit=int(count),
                    domain="" if domain == "Tous" else domain,
                    difficulty="" if difficulty == "Tous" else difficulty,
                )
            else:
                questions = select_random_questions(
                    limit=int(count),
                    domain="" if domain == "Tous" else domain,
                    difficulty="" if difficulty == "Tous" else difficulty,
                )

            if not questions:
                st.warning("Aucune question trouvée avec ces critères.")
            else:
                title = f"{training_type} depuis la banque — {len(questions)} questions"
                quiz = build_quiz_from_bank(
                    questions=questions,
                    title=title,
                    mode=selection_mode,
                    learner_email=learner.get("email", ""),
                )

                st.session_state.v19_auto_quiz = quiz
                st.session_state.v19_auto_answers = {}
                st.session_state.v19_auto_current = 1
                st.session_state.v19_auto_submitted = False
                st.session_state.v19_auto_result = {}
                st.session_state.v19_auto_attempt_id = None
                st.success("Quiz autonome V19 démarré.")
                st.rerun()

        _render_active_quiz(learner)
