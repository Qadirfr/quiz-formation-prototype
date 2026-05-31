from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

import streamlit as st

from utils.autonomous_v19 import evaluate_v19_answer
from utils.db_runtime import get_connection, get_database_mode
from utils.learner_db import (
    finish_attempt,
    get_attempt_answers,
    get_attempts_for_learner_email,
    save_attempt_result,
    start_attempt,
)
from utils.question_bank import (
    build_quiz_from_bank,
    get_question_bank_stats,
    list_bank_difficulties,
    list_bank_domains,
    select_adaptive_questions,
    select_random_questions,
)
from utils.session_db import (
    get_session_answer,
    get_session_live_stats,
    get_training_session,
    get_training_session_by_code,
    join_training_session,
    save_session_answer,
)


def _option_label(index: int) -> str:
    return chr(ord("A") + index)


def _clean_key(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]+", "_", str(value or ""))[:80]


def _render_question_input(question: Dict[str, Any], key_prefix: str, existing: Any = None) -> Any:
    qtype = question.get("type", "")
    options = question.get("options") or []

    if qtype in ["single_choice", "true_false"] and options:
        display_options = [f"{_option_label(i)}. {option}" for i, option in enumerate(options)]
        default_index = 0
        if isinstance(existing, str) and existing:
            for i, item in enumerate(display_options):
                if item.startswith(existing + "."):
                    default_index = i
                    break
        selected = st.radio("Choisis une réponse", display_options, index=default_index, key=f"{key_prefix}_radio")
        return selected.split(".", 1)[0].strip()

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
            answer[left] = st.selectbox(f"Associer : {left}", values, index=index, key=f"{key_prefix}_match_{_clean_key(left)}")
        return answer

    return st.text_area("Ta réponse", value=existing if isinstance(existing, str) else "", height=120, key=f"{key_prefix}_text")


def _recommend_level(percentage: float) -> str:
    if percentage < 50:
        return "Debutant"
    if percentage < 75:
        return "Intermediaire"
    return "Avance"


def _clear_prefix(prefix: str) -> None:
    for key in list(st.session_state.keys()):
        if str(key).startswith(prefix):
            del st.session_state[key]


def _start_bank_quiz(prefix: str, learner: Dict[str, Any], title: str, count: int, domain: str, difficulty: str, adaptive: bool) -> None:
    if adaptive:
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
        return

    quiz = build_quiz_from_bank(
        questions=questions,
        title=title,
        mode="Adaptatif" if adaptive else "Aléatoire",
        learner_email=learner.get("email", ""),
    )
    st.session_state[f"{prefix}_quiz"] = quiz
    st.session_state[f"{prefix}_answers"] = {}
    st.session_state[f"{prefix}_current"] = 1
    st.session_state[f"{prefix}_submitted"] = False
    st.session_state[f"{prefix}_result"] = {}
    st.session_state[f"{prefix}_attempt_id"] = None
    st.rerun()


def _finish_bank_quiz(prefix: str, learner: Dict[str, Any]) -> None:
    quiz = st.session_state.get(f"{prefix}_quiz") or {}
    answers = st.session_state.get(f"{prefix}_answers") or {}
    questions = quiz.get("questions", []) or []

    attempt_id = start_attempt(
        learner_id=int(learner["id"]),
        quiz_id=None,
        quiz_title=quiz.get("quiz_title", "Quiz autonome"),
    )

    total_score = 0.0
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
            total_score += float(evaluation["score"])

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
        details.append({"index": idx, "question": question, "user_answer": user_answer, "evaluation": evaluation})

    percentage = round((total_score / max_score) * 100, 1) if max_score else 0.0
    recommended = _recommend_level(percentage)

    finish_attempt(
        attempt_id=attempt_id,
        score=total_score,
        max_score=max_score,
        percentage=percentage,
        recommended_level=recommended,
        manual_count=manual_count,
    )

    st.session_state[f"{prefix}_submitted"] = True
    st.session_state[f"{prefix}_attempt_id"] = attempt_id
    st.session_state[f"{prefix}_result"] = {
        "score": total_score,
        "max_score": max_score,
        "percentage": percentage,
        "recommended_level": recommended,
        "manual_count": manual_count,
        "details": details,
    }


def _render_bank_quiz(prefix: str, learner: Dict[str, Any]) -> None:
    quiz = st.session_state.get(f"{prefix}_quiz")
    if not quiz:
        return

    result = st.session_state.get(f"{prefix}_result") or {}
    if st.session_state.get(f"{prefix}_submitted") and result:
        st.success(f"Résultat enregistré. Tentative : {st.session_state.get(f'{prefix}_attempt_id')}")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Score global", f"{result.get('percentage', 0)}%")
        c2.metric("Score", f"{result.get('score', 0)} / {result.get('max_score', 0)}")
        c3.metric("Niveau", result.get("recommended_level", "-"))
        c4.metric("À corriger", result.get("manual_count", 0))

        with st.expander("Détail des réponses", expanded=False):
            for item in result.get("details", []):
                evaluation = item["evaluation"]
                question = item["question"]
                status = "Correct" if evaluation["is_correct"] is True else "Incorrect" if evaluation["is_correct"] is False else "À corriger"
                st.markdown(f"#### Q{item['index']} — {status}")
                st.write(question.get("question", ""))
                st.write("Réponse apprenant :")
                st.code(json.dumps(item["user_answer"], ensure_ascii=False, indent=2))
                st.write("Correction :")
                st.code(json.dumps(evaluation["correct_answer"], ensure_ascii=False, indent=2))
                if evaluation.get("selected_feedback"):
                    st.warning(evaluation["selected_feedback"])
                if evaluation.get("correct_feedback"):
                    st.info(evaluation["correct_feedback"])

        if st.button("Faire un nouveau quiz", width="stretch", key=f"{prefix}_new"):
            _clear_prefix(prefix)
            st.rerun()
        return

    questions = quiz.get("questions", []) or []
    answers = st.session_state.setdefault(f"{prefix}_answers", {})
    current = max(1, min(int(st.session_state.get(f"{prefix}_current", 1)), len(questions)))
    st.session_state[f"{prefix}_current"] = current

    answered_count = len([v for v in answers.values() if v not in [None, "", {}]])
    st.progress(answered_count / len(questions))
    st.caption(f"Question {current} / {len(questions)} — {answered_count} réponse(s) enregistrée(s)")

    question = questions[current - 1]
    st.markdown(f"### Question {current}")
    st.write(question.get("question", ""))

    answer = _render_question_input(question, f"{prefix}_{current}", answers.get(str(current)))

    cols = st.columns(3)
    with cols[0]:
        if st.button("Enregistrer", type="primary", width="stretch", key=f"{prefix}_save"):
            answers[str(current)] = answer
            st.session_state[f"{prefix}_answers"] = answers
            st.success("Réponse enregistrée.")
    with cols[1]:
        if st.button("Précédente", width="stretch", disabled=current <= 1, key=f"{prefix}_prev"):
            answers[str(current)] = answer
            st.session_state[f"{prefix}_answers"] = answers
            st.session_state[f"{prefix}_current"] = current - 1
            st.rerun()
    with cols[2]:
        if st.button("Suivante", width="stretch", disabled=current >= len(questions), key=f"{prefix}_next"):
            answers[str(current)] = answer
            st.session_state[f"{prefix}_answers"] = answers
            st.session_state[f"{prefix}_current"] = current + 1
            st.rerun()

    unanswered = [str(i) for i in range(1, len(questions) + 1) if answers.get(str(i)) in [None, "", {}]]
    if unanswered:
        st.info(f"Questions sans réponse enregistrée : {', '.join(unanswered[:15])}" + ("..." if len(unanswered) > 15 else ""))

    if st.button("Terminer et enregistrer mes résultats", type="primary", width="stretch", disabled=bool(unanswered), key=f"{prefix}_finish"):
        _finish_bank_quiz(prefix, learner)
        st.rerun()

    if st.button("Abandonner", width="stretch", key=f"{prefix}_cancel"):
        _clear_prefix(prefix)
        st.rerun()


def _filters(prefix: str, default_count: int, exam_mode: bool = False) -> Dict[str, Any]:
    stats = get_question_bank_stats()
    total = int(stats.get("total", 0) or 0)
    domains = ["Tous"] + list_bank_domains()
    difficulties = ["Tous"] + list_bank_difficulties()

    if total <= 0:
        st.warning("La banque de questions est vide.")
        return {"ok": False}

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        count = st.number_input("Nombre de questions", min_value=1, max_value=max(1, min(80, total)), value=min(default_count, total), step=1, key=f"{prefix}_count")
    with c2:
        domain = st.selectbox("Domaine", domains, key=f"{prefix}_domain")
    with c3:
        difficulty = st.selectbox("Niveau", difficulties, key=f"{prefix}_difficulty")
    with c4:
        adaptive = st.toggle("Adaptatif", value=not exam_mode, key=f"{prefix}_adaptive")

    return {"ok": True, "count": int(count), "domain": domain, "difficulty": difficulty, "adaptive": adaptive}


def render_training_tab(learner: Dict[str, Any]) -> None:
    st.subheader("S’entraîner")
    st.caption("Génère automatiquement un entraînement depuis la banque de questions.")

    prefix = "v20_training"
    settings = _filters(prefix, default_count=10, exam_mode=False)
    if settings.get("ok"):
        if st.button("Démarrer l’entraînement", type="primary", width="stretch", key=f"{prefix}_start"):
            _start_bank_quiz(
                prefix,
                learner,
                title=f"Entraînement autonome — {settings['count']} questions",
                count=settings["count"],
                domain=settings["domain"],
                difficulty=settings["difficulty"],
                adaptive=settings["adaptive"],
            )
    _render_bank_quiz(prefix, learner)


def render_exam_tab(learner: Dict[str, Any]) -> None:
    st.subheader("Passer un examen autonome")
    st.caption("Format cadré depuis la banque. Idéal pour simuler un examen de 40 questions.")

    prefix = "v20_exam"
    settings = _filters(prefix, default_count=40, exam_mode=True)
    if settings.get("ok"):
        if st.button("Démarrer l’examen autonome", type="primary", width="stretch", key=f"{prefix}_start"):
            _start_bank_quiz(
                prefix,
                learner,
                title=f"Examen autonome — {settings['count']} questions",
                count=settings["count"],
                domain=settings["domain"],
                difficulty=settings["difficulty"],
                adaptive=settings["adaptive"],
            )
    _render_bank_quiz(prefix, learner)


def _join_session(prefix: str, learner: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    code = st.text_input("Code session", key=f"{prefix}_code").strip().upper()
    if st.button("Rejoindre", type="primary", width="stretch", key=f"{prefix}_join"):
        session = get_training_session_by_code(code)
        if not session:
            st.error("Session introuvable.")
        elif session.get("status") == "closed":
            st.warning("Cette session est clôturée.")
        else:
            participant = join_training_session(session["id"], int(learner["id"]))
            st.session_state[f"{prefix}_session_id"] = session["id"]
            st.session_state[f"{prefix}_participant_id"] = participant["id"]
            st.success(f"Session rejointe : {session['title']}")
            st.rerun()

    session_id = st.session_state.get(f"{prefix}_session_id")
    if not session_id:
        return None
    return get_training_session(int(session_id))


def render_session_autonomous_tab(learner: Dict[str, Any]) -> None:
    st.subheader("Session autonome")
    st.caption("Le formateur fournit un code. Tu avances à ton rythme. Les résultats sont rattachés à la session.")

    prefix = "v20_session_auto"
    session = _join_session(prefix, learner)
    if not session:
        return

    participant_id = st.session_state.get(f"{prefix}_participant_id")
    questions = session.get("questions", []) or []
    if not questions:
        st.warning("Cette session ne contient aucune question.")
        return

    current = max(1, min(int(st.session_state.get(f"{prefix}_current", 1)), len(questions)))
    st.session_state[f"{prefix}_current"] = current
    question = questions[current - 1]
    existing_answer = get_session_answer(session["id"], participant_id, current)

    st.markdown(f"### {session.get('title', '')}")
    st.caption(f"Question {current} / {len(questions)}")
    st.write(question.get("question", ""))

    existing_value = None
    if existing_answer:
        try:
            existing_value = json.loads(existing_answer.get("user_answer_json") or "null")
        except Exception:
            existing_value = existing_answer.get("user_answer_json")

    answer = _render_question_input(question, f"{prefix}_{current}", existing_value)

    cols = st.columns(3)
    with cols[0]:
        if st.button("Enregistrer la réponse", type="primary", width="stretch", key=f"{prefix}_save"):
            evaluation = evaluate_v19_answer(question, answer)
            save_session_answer(
                session_id=session["id"],
                participant_id=participant_id,
                learner_id=int(learner["id"]),
                question_index=current,
                question=question,
                user_answer=answer,
                correct_answer=evaluation["correct_answer"],
                is_correct=evaluation["is_correct"],
                score=float(evaluation["score"]),
                selected_feedback=evaluation.get("selected_feedback", ""),
                correct_feedback=evaluation.get("correct_feedback", ""),
            )
            st.success("Réponse enregistrée dans la session.")
            st.rerun()
    with cols[1]:
        if st.button("Précédente", width="stretch", disabled=current <= 1, key=f"{prefix}_prev"):
            st.session_state[f"{prefix}_current"] = current - 1
            st.rerun()
    with cols[2]:
        if st.button("Suivante", width="stretch", disabled=current >= len(questions), key=f"{prefix}_next"):
            st.session_state[f"{prefix}_current"] = current + 1
            st.rerun()


def render_live_session_tab(learner: Dict[str, Any]) -> None:
    st.subheader("Session live / dirigée")
    st.caption("Le formateur pilote les questions. Utilise Actualiser pour suivre l’avancement.")

    prefix = "v20_session_live"
    session = _join_session(prefix, learner)
    if not session:
        return

    if st.button("Actualiser la session", width="stretch", key=f"{prefix}_refresh"):
        st.rerun()

    participant_id = st.session_state.get(f"{prefix}_participant_id")
    questions = session.get("questions", []) or []
    if not questions:
        st.warning("Cette session ne contient aucune question.")
        return

    current_index = max(0, min(int(session.get("current_question_index") or 0), len(questions) - 1))
    question_number = current_index + 1
    question = questions[current_index]
    existing = get_session_answer(session["id"], participant_id, question_number)

    st.markdown(f"### {session.get('title', '')}")
    st.caption(f"Question pilotée par le formateur : {question_number} / {len(questions)}")
    st.write(question.get("question", ""))

    if existing:
        st.success("Réponse enregistrée pour cette question.")
        if session.get("show_correction"):
            if existing.get("is_correct") is True:
                st.success(existing.get("correct_feedback") or "Bonne réponse.")
            elif existing.get("is_correct") is False:
                st.error(existing.get("selected_feedback") or "Réponse incorrecte.")
                st.info(existing.get("correct_feedback") or "Correction disponible.")
            else:
                st.warning("Réponse à corriger manuellement.")
        else:
            st.info("Correction masquée pour le moment.")
        return

    answer = _render_question_input(question, f"{prefix}_{question_number}")
    if st.button("Valider ma réponse", type="primary", width="stretch", key=f"{prefix}_submit"):
        evaluation = evaluate_v19_answer(question, answer)
        save_session_answer(
            session_id=session["id"],
            participant_id=participant_id,
            learner_id=int(learner["id"]),
            question_index=question_number,
            question=question,
            user_answer=answer,
            correct_answer=evaluation["correct_answer"],
            is_correct=evaluation["is_correct"],
            score=float(evaluation["score"]),
            selected_feedback=evaluation.get("selected_feedback", ""),
            correct_feedback=evaluation.get("correct_feedback", ""),
        )
        st.success("Réponse enregistrée.")
        st.rerun()


def _infer_mode(title: str) -> str:
    low = str(title or "").lower()
    if "examen" in low:
        return "Examen autonome"
    if "entrainement" in low or "entraînement" in low:
        return "Entraînement"
    if "session" in low:
        return "Session"
    return "Autre"


def _attempts_dataframe(attempts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = []
    for attempt in attempts:
        rows.append(
            {
                "ID": attempt.get("id"),
                "Date": str(attempt.get("started_at") or attempt.get("created_at") or "")[:19],
                "Examen / quiz": attempt.get("quiz_title", ""),
                "Mode": _infer_mode(attempt.get("quiz_title", "")),
                "Score": f"{attempt.get('score', 0)} / {attempt.get('max_score', 0)}",
                "Pourcentage": float(attempt.get("percentage") or 0),
                "Niveau": attempt.get("recommended_level", ""),
                "À corriger": attempt.get("manual_count", 0),
            }
        )
    return rows


def _aggregate_answers(attempt_ids: List[int]) -> Dict[str, Dict[str, float]]:
    by_domain: Dict[str, Dict[str, float]] = {}
    by_cognitive: Dict[str, Dict[str, float]] = {}

    for attempt_id in attempt_ids:
        for answer in get_attempt_answers(int(attempt_id)):
            if answer.get("is_correct") is None:
                continue
            score = float(answer.get("score") or 0)
            domain = answer.get("domain") or "Non classé"
            cognitive = answer.get("cognitive_level") or "Non renseigné"

            by_domain.setdefault(domain, {"score": 0.0, "max": 0.0})
            by_domain[domain]["score"] += score
            by_domain[domain]["max"] += 1.0

            by_cognitive.setdefault(cognitive, {"score": 0.0, "max": 0.0})
            by_cognitive[cognitive]["score"] += score
            by_cognitive[cognitive]["max"] += 1.0

    return {"domain": by_domain, "cognitive": by_cognitive}


def _display_aggregate(title: str, data: Dict[str, Dict[str, float]]) -> None:
    st.markdown(f"#### {title}")
    if not data:
        st.info("Aucune donnée consolidée disponible.")
        return
    for label, values in sorted(data.items()):
        max_score = values.get("max", 0) or 0
        pct = round((values.get("score", 0) / max_score) * 100, 1) if max_score else 0
        st.write(f"**{label}** — {pct}% ({values.get('score', 0)} / {max_score})")
        st.progress(min(1.0, max(0.0, pct / 100)))


def render_results_tab(learner: Dict[str, Any]) -> None:
    st.subheader("Mes résultats")
    st.caption("Vue consolidée de tes tentatives autonomes et examens.")

    attempts = get_attempts_for_learner_email(learner.get("email", ""), limit=500)
    if not attempts:
        st.info("Aucun résultat enregistré pour le moment.")
        return

    rows = _attempts_dataframe(attempts)
    titles = ["Tous"] + sorted({row["Examen / quiz"] for row in rows if row["Examen / quiz"]})
    modes = ["Tous"] + sorted({row["Mode"] for row in rows if row["Mode"]})

    c1, c2 = st.columns(2)
    with c1:
        selected_title = st.selectbox("Filtrer par examen / quiz", titles, key="v20_results_title")
    with c2:
        selected_mode = st.selectbox("Filtrer par mode", modes, key="v20_results_mode")

    filtered = rows
    if selected_title != "Tous":
        filtered = [row for row in filtered if row["Examen / quiz"] == selected_title]
    if selected_mode != "Tous":
        filtered = [row for row in filtered if row["Mode"] == selected_mode]

    if not filtered:
        st.warning("Aucun résultat ne correspond aux filtres.")
        return

    avg = round(sum(row["Pourcentage"] for row in filtered) / len(filtered), 1)
    best = max(row["Pourcentage"] for row in filtered)

    c1, c2, c3 = st.columns(3)
    c1.metric("Tentatives", len(filtered))
    c2.metric("Score moyen", f"{avg}%")
    c3.metric("Meilleur score", f"{best}%")

    st.dataframe(filtered, width="stretch", hide_index=True)

    attempt_ids = [int(row["ID"]) for row in filtered if row.get("ID")]
    aggregates = _aggregate_answers(attempt_ids)

    _display_aggregate("Consolidé par domaine", aggregates["domain"])
    _display_aggregate("Consolidé par compétence cognitive", aggregates["cognitive"])

    with st.expander("Détail d’une tentative", expanded=False):
        selected_attempt = st.selectbox(
            "Tentative",
            attempt_ids,
            format_func=lambda x: f"Tentative #{x}",
            key="v20_detail_attempt",
        )
        answers = get_attempt_answers(int(selected_attempt))
        for answer in answers:
            st.markdown(f"**Q{answer.get('question_index')} — {answer.get('question_text', '')}**")
            st.write("Réponse :")
            st.code(answer.get("user_answer_json", ""))
            st.write("Correction :")
            st.code(answer.get("correct_answer_json", ""))
            if answer.get("selected_feedback"):
                st.warning(answer.get("selected_feedback"))
            if answer.get("correct_feedback"):
                st.info(answer.get("correct_feedback"))


def render_learner_v20(learner: Optional[Dict[str, Any]]) -> None:
    if not learner:
        st.warning("Connecte-toi comme apprenant pour accéder à l’espace apprenant.")
        return

    st.markdown("## Espace apprenant")
    st.caption("Navigation simplifiée : entraînement, examen autonome, sessions et résultats.")

    tab_training, tab_exam, tab_session_auto, tab_live, tab_results = st.tabs(
        [
            "S’entraîner",
            "Examen autonome",
            "Session autonome",
            "Session live",
            "Mes résultats",
        ]
    )

    with tab_training:
        render_training_tab(learner)

    with tab_exam:
        render_exam_tab(learner)

    with tab_session_auto:
        render_session_autonomous_tab(learner)

    with tab_live:
        render_live_session_tab(learner)

    with tab_results:
        render_results_tab(learner)
