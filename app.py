from __future__ import annotations

import hashlib
import math
import json
import os
import re
import unicodedata
from typing import Any, Dict, List, Optional

import matplotlib.pyplot as plt
import streamlit as st

# Auto-refresh désactivé en V20.1 pour éviter les rafraîchissements permanents.
st_autorefresh = None

from utils.database import delete_quiz, init_db, list_saved_quizzes, load_quiz, save_quiz
from utils.export_utils import quiz_to_csv_bytes, quiz_to_json_bytes, quiz_to_markdown, quiz_to_markdown_bytes
from utils.file_reader import clean_training_text, read_uploaded_file
from utils.learner_db import (
    create_or_get_learner,
    finish_attempt,
    get_attempt_answers,
    get_attempts_for_learner_email,
    get_attempts_summary,
    init_learner_db,
    save_attempt_result,
    start_attempt,
)
from utils.quiz_agents import QuizConfig, analyze_training_content, orchestrate_quiz_generation
from utils.table_import import read_quiz_table, template_csv_bytes
from utils.session_db import (
    create_training_session,
    generate_session_code,
    get_session_answer,
    get_session_live_stats,
    get_session_participant_summary,
    get_training_session,
    get_training_session_by_code,
    init_session_db,
    join_training_session,
    list_session_participants,
    list_training_sessions,
    save_session_answer,
    set_session_show_correction,
    update_session_position,
    update_session_status,
)
from utils.question_bank import (
    add_quiz_to_bank,
    build_quiz_from_bank,
    get_question_bank_stats,
    init_question_bank_db,
    list_bank_difficulties,
    list_bank_domains,
    select_adaptive_questions,
    select_random_questions,
)


st.set_page_config(
    page_title="Plateforme quiz local",
    page_icon="Q",
    layout="wide",
)

init_db()
init_learner_db()
init_question_bank_db()
init_session_db()

LEARNER_ACCESS_CODE = os.environ.get("QUIZ_LEARNER_CODE", "CIVIQUE2026")
TRAINER_PASSWORD = os.environ.get("QUIZ_TRAINER_PASSWORD", "formateur123")


def check_trainer_password(password: str) -> bool:
    expected = hashlib.sha256(TRAINER_PASSWORD.encode("utf-8")).hexdigest()
    provided = hashlib.sha256(password.encode("utf-8")).hexdigest()
    return provided == expected


def init_state() -> None:
    defaults = {
        "quiz": None,
        "analysis": None,
        "source_text": "",
        "last_saved_id": None,
        "learner": None,
        "active_attempt_id": None,
        "active_quiz_for_test": None,
        "role": None,
        "last_completed_attempt_id": None,
        "active_directed_session_id": None,
        "active_directed_participant_id": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


init_state()






def persist_learner_url_context(session_code: str = "") -> None:
    learner = st.session_state.get("learner")
    if not learner:
        return

    params = {
        "role": "learner",
        "learner_email": learner.get("email", ""),
        "learner_name": learner.get("name", ""),
        "learner_group": learner.get("group_name", "") or "",
    }

    if session_code:
        params["session_code"] = session_code
    elif st.query_params.get("session_code"):
        params["session_code"] = st.query_params.get("session_code")

    try:
        st.query_params.update(params)
    except Exception:
        pass


def restore_learner_from_url_context() -> None:
    if st.session_state.get("role") is not None:
        return

    try:
        role = st.query_params.get("role")
        email = st.query_params.get("learner_email")
        name = st.query_params.get("learner_name") or "Apprenant"
        group = st.query_params.get("learner_group") or ""
        session_code = st.query_params.get("session_code") or ""
    except Exception:
        return

    if role != "learner" or not email:
        return

    try:
        learner = create_or_get_learner(name=name, email=email, group_name=group)
        st.session_state.learner = learner
        st.session_state.role = "learner"

        if session_code:
            session = get_training_session_by_code(session_code)
            if session and session.get("status") != "closed":
                participant = join_training_session(session["id"], learner["id"])
                st.session_state.active_directed_session_id = session["id"]
                st.session_state.active_directed_participant_id = participant["id"]
    except Exception:
        pass

restore_learner_from_url_context()


def logout() -> None:
    for key in ["role", "learner", "active_attempt_id", "active_quiz_for_test", "last_completed_attempt_id"]:
        st.session_state[key] = None
    st.rerun()


def normalize_text(value: Any) -> str:
    text = "" if value is None else str(value)
    text = text.strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_answer(value: Any) -> str:
    return normalize_text(value)


def parse_json_text(value: str) -> Any:
    try:
        return json.loads(value)
    except Exception:
        return value


def option_label(index: int) -> str:
    return chr(65 + index)


def resolve_answer_label_and_text(answer: Any, options: List[str]) -> tuple[str, str]:
    answer_text = "" if answer is None else str(answer).strip()

    if len(answer_text) == 1 and answer_text.upper().isalpha():
        label = answer_text.upper()
        idx = ord(label) - 65
        if 0 <= idx < len(options):
            return label, str(options[idx])
        return label, ""

    normalized_answer = normalize_answer(answer_text)
    for idx, option in enumerate(options):
        if normalize_answer(option) == normalized_answer:
            return option_label(idx), str(option)

    if normalized_answer in ["vrai", "true"]:
        return "VRAI", "Vrai"
    if normalized_answer in ["faux", "false"]:
        return "FAUX", "Faux"

    return "", answer_text


def get_feedback_for_label(question: Dict[str, Any], label: str, text: str) -> str:
    feedbacks = question.get("feedbacks") or {}
    if not isinstance(feedbacks, dict):
        feedbacks = {}

    label_upper = label.upper() if label else ""
    text_upper = normalize_answer(text).upper()

    if label_upper in feedbacks:
        return str(feedbacks[label_upper])

    if text_upper in ["VRAI", "TRUE"] and "VRAI" in feedbacks:
        return str(feedbacks["VRAI"])
    if text_upper in ["FAUX", "FALSE"] and "FAUX" in feedbacks:
        return str(feedbacks["FAUX"])

    # Compatibilite avec des anciens imports qui auraient stocke feedback_a directement.
    if label_upper:
        direct_key = f"feedback_{label_upper.lower()}"
        if question.get(direct_key):
            return str(question.get(direct_key))

    return ""


def is_single_choice_correct(user_answer: str, correct_answer: str, options: List[str]) -> bool:
    ua = normalize_answer(user_answer)
    ca = normalize_answer(correct_answer)

    if not ua or not ca:
        return False

    if ua == ca:
        return True

    user_label, user_text = resolve_answer_label_and_text(user_answer, options)
    correct_label, correct_text = resolve_answer_label_and_text(correct_answer, options)

    if user_label and correct_label and user_label == correct_label:
        return True

    if correct_text and normalize_answer(user_text) == normalize_answer(correct_text):
        return True

    return False


def short_answer_matches(user_answer: Any, question: Dict[str, Any]) -> Optional[bool]:
    user_norm = normalize_answer(user_answer)
    correct_answer = question.get("correct_answer", "")
    correct_norm = normalize_answer(correct_answer)

    accepted = question.get("accepted_answers") or []
    if isinstance(accepted, str):
        accepted = [item.strip() for item in re.split(r"[|;]", accepted) if item.strip()]

    accepted_norms = [normalize_answer(item) for item in accepted]
    if correct_norm:
        accepted_norms.append(correct_norm)

    if not user_norm:
        return False

    if not accepted_norms:
        return None

    for accepted_norm in accepted_norms:
        if not accepted_norm:
            continue
        if user_norm == accepted_norm:
            return True
        if len(accepted_norm) >= 5 and (accepted_norm in user_norm or user_norm in accepted_norm):
            return True

    # Si une liste de reponses acceptees est fournie, on peut corriger automatiquement.
    if accepted:
        return False

    # Sinon, on ne sanctionne pas automatiquement une reponse courte.
    return None


def evaluate_answer(question: Dict[str, Any], user_answer: Any) -> Dict[str, Any]:
    qtype = question.get("type", "")
    options = question.get("options") or []
    correct_answer = question.get("correct_answer", "")

    if qtype in ["single_choice", "true_false"]:
        is_ok = is_single_choice_correct(str(user_answer), str(correct_answer), options)
        user_label, user_text = resolve_answer_label_and_text(user_answer, options)
        correct_label, correct_text = resolve_answer_label_and_text(correct_answer, options)

        selected_feedback = get_feedback_for_label(question, user_label, user_text)
        correct_feedback = get_feedback_for_label(question, correct_label, correct_text)

        if not selected_feedback:
            selected_feedback = f"Réponse choisie : {user_text or user_answer}."
        if not correct_feedback:
            correct_feedback = question.get("explanation", "") or f"La bonne réponse est {correct_label or correct_answer}."

        return {
            "score": 1.0 if is_ok else 0.0,
            "is_correct": is_ok,
            "correct_answer": correct_answer,
            "selected_feedback": selected_feedback,
            "correct_feedback": correct_feedback,
        }

    if qtype == "matching":
        pairs = question.get("pairs") or []
        expected = {p.get("left", ""): p.get("right", "") for p in pairs}
        given = user_answer if isinstance(user_answer, dict) else {}

        if not expected:
            return {
                "score": 0.0,
                "is_correct": False,
                "correct_answer": expected,
                "selected_feedback": "Aucune paire de correction n'a été trouvée.",
                "correct_feedback": question.get("explanation", ""),
            }

        correct_count = 0
        wrong_lines = []
        for left, right in expected.items():
            given_right = given.get(left, "")
            if normalize_answer(given_right) == normalize_answer(right):
                correct_count += 1
            else:
                wrong_lines.append(f"{left} : tu as choisi « {given_right} », la réponse attendue était « {right} ».")

        score = correct_count / len(expected)
        if wrong_lines:
            selected_feedback = " ".join(wrong_lines)
        else:
            selected_feedback = "Toutes les associations sont correctes."

        correct_feedback = "Correction attendue : " + "; ".join(
            f"{left} -> {right}" for left, right in expected.items()
        )

        return {
            "score": score,
            "is_correct": score == 1.0,
            "correct_answer": expected,
            "selected_feedback": selected_feedback,
            "correct_feedback": correct_feedback,
        }

    if qtype == "short_answer":
        match = short_answer_matches(user_answer, question)
        correct_feedback = question.get("explanation", "") or f"Réponse attendue : {correct_answer}"
        if match is True:
            return {
                "score": 1.0,
                "is_correct": True,
                "correct_answer": correct_answer,
                "selected_feedback": "Réponse acceptée.",
                "correct_feedback": correct_feedback,
            }
        if match is False:
            return {
                "score": 0.0,
                "is_correct": False,
                "correct_answer": correct_answer,
                "selected_feedback": "La réponse ne correspond pas aux réponses acceptées.",
                "correct_feedback": correct_feedback,
            }

        return {
            "score": 0.0,
            "is_correct": None,
            "correct_answer": correct_answer,
            "selected_feedback": "Réponse enregistrée, à corriger manuellement.",
            "correct_feedback": correct_feedback,
        }

    return {
        "score": 0.0,
        "is_correct": False,
        "correct_answer": correct_answer,
        "selected_feedback": "Type de question non reconnu.",
        "correct_feedback": question.get("explanation", ""),
    }


def recommendation_from_percentage(percentage: float) -> str:
    if percentage < 50:
        return "Debutant"
    if percentage < 80:
        return "Intermediaire"
    return "Avance"


def build_config(
    provider: str,
    ollama_base_url: str,
    model_name: str,
    difficulty: str,
    question_types: List[str],
    number_of_questions: int,
    audience: str,
    assessment_goal: str,
    cognitive_focus: str,
) -> QuizConfig:
    return QuizConfig(
        provider=provider,
        ollama_base_url=ollama_base_url,
        model_name=model_name,
        difficulty=difficulty,
        question_types=question_types,
        number_of_questions=number_of_questions,
        audience=audience,
        assessment_goal=assessment_goal,
        cognitive_focus=cognitive_focus,
    )


def quality_label(score: int) -> str:
    if score >= 80:
        return "Bon"
    if score >= 70:
        return "Acceptable"
    return "A relire"


def status_label(is_correct: Optional[bool]) -> str:
    if is_correct is None:
        return "À corriger"
    if is_correct:
        return "Correct"
    return "Incorrect"


def compute_domain_summary(details: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    summary: Dict[str, Dict[str, Any]] = {}

    for answer in details:
        domain = answer.get("domain") or "Non classé"
        item = summary.setdefault(
            domain,
            {
                "score": 0.0,
                "max_score": 0.0,
                "manual_count": 0,
                "total_questions": 0,
                "incorrect_questions": [],
                "remediations": set(),
                "objectives": set(),
                "concepts": set(),
            },
        )

        item["total_questions"] += 1

        if answer.get("is_correct") is None:
            item["manual_count"] += 1
        else:
            item["score"] += float(answer.get("score") or 0)
            item["max_score"] += 1.0
            if not answer.get("is_correct"):
                item["incorrect_questions"].append(answer)

        remediation = (answer.get("remediation") or "").strip()
        if remediation and (answer.get("is_correct") is False):
            item["remediations"].add(remediation)

        objective = (answer.get("learning_objective") or "").strip()
        if objective:
            item["objectives"].add(objective)

        concept = (answer.get("concept_evaluated") or "").strip()
        if concept and (answer.get("is_correct") is False):
            item["concepts"].add(concept)

    for item in summary.values():
        if item["max_score"]:
            item["percentage"] = round((item["score"] / item["max_score"]) * 100, 1)
        else:
            item["percentage"] = 0.0
        item["remediations"] = sorted(item["remediations"])
        item["objectives"] = sorted(item["objectives"])
        item["concepts"] = sorted(item["concepts"])

    return summary


def compute_cognitive_summary(details: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    summary: Dict[str, Dict[str, Any]] = {}

    for answer in details:
        level = answer.get("cognitive_level") or "Non renseigné"
        item = summary.setdefault(level, {"score": 0.0, "max_score": 0.0, "manual_count": 0, "total_questions": 0})
        item["total_questions"] += 1

        if answer.get("is_correct") is None:
            item["manual_count"] += 1
        else:
            item["score"] += float(answer.get("score") or 0)
            item["max_score"] += 1.0

    for item in summary.values():
        if item["max_score"]:
            item["percentage"] = round((item["score"] / item["max_score"]) * 100, 1)
        else:
            item["percentage"] = 0.0

    return summary


def build_improvement_plan(domain_summary: Dict[str, Dict[str, Any]], cognitive_summary: Dict[str, Dict[str, Any]]) -> List[str]:
    plan = []

    weak_domains = [
        (domain, data)
        for domain, data in domain_summary.items()
        if data.get("max_score", 0) > 0 and data.get("percentage", 0) < 80
    ]
    weak_domains.sort(key=lambda kv: (kv[1].get("percentage", 0), -kv[1].get("total_questions", 0)))

    for domain, data in weak_domains[:3]:
        pct = data.get("percentage", 0)
        if pct < 50:
            prefix = "Priorité forte"
            action = "reprendre les bases avec une fiche de synthèse, puis refaire un quiz court ciblé."
        elif pct < 70:
            prefix = "À consolider"
            action = "revoir les erreurs, refaire des questions d'entraînement et vérifier les notions confondues."
        else:
            prefix = "Consolidation légère"
            action = "faire quelques questions supplémentaires pour stabiliser les acquis."

        concepts = ", ".join(data.get("concepts", [])[:3])
        if concepts:
            concept_text = f" Notions à reprendre : {concepts}."
        else:
            concept_text = ""

        if data.get("remediations"):
            remediation = " ".join(data["remediations"][:2])
        else:
            remediation = action

        plan.append(f"{prefix} — {domain} : {pct}% de réussite. {remediation}{concept_text}")

    weak_cognitive = [
        (level, data)
        for level, data in cognitive_summary.items()
        if data.get("max_score", 0) > 0 and data.get("percentage", 0) < 70
    ]
    weak_cognitive.sort(key=lambda kv: kv[1].get("percentage", 0))

    if weak_cognitive:
        level, data = weak_cognitive[0]
        plan.append(
            f"Compétence cognitive à travailler — {level} : {data.get('percentage', 0)}%. "
            "Prévoir des exercices plus guidés sur ce niveau avant de passer au niveau supérieur."
        )

    if not plan:
        plan.append("Aucun domaine prioritaire détecté sur les questions corrigées automatiquement. Prévoir un entraînement d'entretien pour maintenir le niveau.")

    return plan


def _chart_labels_values(summary: Dict[str, Dict[str, Any]]) -> tuple[List[str], List[float]]:
    labels = []
    values = []
    for label, data in summary.items():
        if data.get("max_score", 0) > 0:
            labels.append(label)
            values.append(float(data.get("percentage", 0)))
    return labels, values


def render_pie_chart(domain_summary: Dict[str, Dict[str, Any]]) -> None:
    labels, values = _chart_labels_values(domain_summary)
    if not labels:
        st.info("Camembert indisponible : aucun domaine corrigé automatiquement.")
        return

    # Le camembert représente la part relative des points obtenus par domaine.
    point_labels = []
    point_values = []
    for label, data in domain_summary.items():
        if data.get("score", 0) > 0:
            point_labels.append(label)
            point_values.append(float(data.get("score", 0)))

    if not point_values:
        point_labels = labels
        point_values = [1 for _ in labels]

    fig, ax = plt.subplots(figsize=(4.8, 4.8))
    ax.pie(point_values, labels=point_labels, autopct="%1.0f%%", startangle=90)
    ax.axis("equal")
    st.pyplot(fig)


def render_radar_chart(domain_summary: Dict[str, Dict[str, Any]]) -> None:
    labels, values = _chart_labels_values(domain_summary)
    if len(labels) < 2:
        st.info("Radar indisponible : il faut au moins 2 domaines renseignés.")
        return

    angles = [n / float(len(labels)) * 2 * math.pi for n in range(len(labels))]
    values_closed = values + values[:1]
    angles_closed = angles + angles[:1]

    fig = plt.figure(figsize=(5.8, 5.8))
    ax = plt.subplot(111, polar=True)
    ax.plot(angles_closed, values_closed, linewidth=2)
    ax.fill(angles_closed, values_closed, alpha=0.15)
    ax.set_xticks(angles)
    ax.set_xticklabels(labels)
    ax.set_ylim(0, 100)
    ax.set_yticks([20, 40, 60, 80, 100])
    ax.set_yticklabels(["20", "40", "60", "80", "100"])
    st.pyplot(fig)


def render_cognitive_bar_chart(cognitive_summary: Dict[str, Dict[str, Any]]) -> None:
    labels, values = _chart_labels_values(cognitive_summary)
    if not labels:
        st.info("Graphique cognitif indisponible : aucun niveau cognitif corrigé automatiquement.")
        return

    fig, ax = plt.subplots(figsize=(7, 3.8))
    ax.bar(labels, values)
    ax.set_ylim(0, 100)
    ax.set_ylabel("Réussite (%)")
    ax.set_xlabel("Compétence cognitive")
    ax.set_title("Résultat par compétence cognitive")
    for index, value in enumerate(values):
        ax.text(index, min(value + 2, 100), f"{value:.0f}%", ha="center")
    plt.xticks(rotation=20, ha="right")
    st.pyplot(fig)


def render_domain_table(domain_summary: Dict[str, Dict[str, Any]]) -> None:
    rows = []
    for domain, data in sorted(domain_summary.items(), key=lambda kv: kv[1].get("percentage", 0)):
        rows.append(
            {
                "Domaine": domain,
                "Réussite": f"{data.get('percentage', 0)}%",
                "Score": f"{round(data.get('score', 0), 2)} / {round(data.get('max_score', 0), 2)}",
                "Questions": data.get("total_questions", 0),
                "À corriger": data.get("manual_count", 0),
            }
        )

    if rows:
        st.dataframe(rows, width="stretch", hide_index=True)
    else:
        st.info("Aucun domaine exploitable.")


def render_attempt_report(attempt: Dict[str, Any], details: List[Dict[str, Any]], show_learner: bool = True) -> None:
    percentage = round(float(attempt.get("percentage") or 0), 1)
    recommended_level = attempt.get("recommended_level") or recommendation_from_percentage(percentage)
    score = round(float(attempt.get("score") or 0), 2)
    max_score = round(float(attempt.get("max_score") or 0), 2)

    domain_summary = compute_domain_summary(details)
    cognitive_summary = compute_cognitive_summary(details)
    improvement_plan = build_improvement_plan(domain_summary, cognitive_summary)

    st.markdown("### Synthèse visuelle")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Score global", f"{percentage}%")
    col2.metric("Niveau conseillé", recommended_level)
    col3.metric("Score", f"{score} / {max_score}")
    col4.metric("À corriger", attempt.get("manual_count") or 0)

    st.progress(min(max(percentage / 100, 0), 1))

    if show_learner:
        st.write(f"**Apprenant :** {attempt.get('learner_name', '')} ({attempt.get('learner_email', '')})")
        st.write(f"**Groupe :** {attempt.get('group_name') or '-'}")

    st.write(f"**Quiz :** {attempt.get('quiz_title', '')}")

    st.markdown("### Visualisation des résultats")
    chart_col1, chart_col2 = st.columns(2)

    with chart_col1:
        st.markdown("#### Répartition des points obtenus")
        render_pie_chart(domain_summary)

    with chart_col2:
        st.markdown("#### Radar par domaine")
        render_radar_chart(domain_summary)

    st.markdown("#### Compétences cognitives")
    render_cognitive_bar_chart(cognitive_summary)

    st.markdown("### Résultat par domaine")
    render_domain_table(domain_summary)

    st.markdown("### Pistes de travail personnalisées")
    for item in improvement_plan:
        st.warning(item)

    st.markdown("### Réponses détaillées")
    for answer in details:
        ok = answer.get("is_correct")
        label = status_label(ok)

        if ok is True:
            box = st.success
        elif ok is False:
            box = st.error
        else:
            box = st.warning

        with st.expander(
            f"Q{answer['question_index']} — {label} — {answer.get('domain') or 'Non classé'} — score {round(float(answer.get('score') or 0), 2)}",
            expanded=ok is False,
        ):
            st.write(answer["question_text"])
            st.caption(f"Réponse apprenant : {answer['user_answer_json']}")
            st.caption(f"Correction : {answer['correct_answer_json']}")

            if ok is False:
                box(answer.get("selected_feedback") or "La réponse choisie n'est pas la réponse attendue.")
                st.info(answer.get("correct_feedback") or answer.get("explanation") or "Aucune explication détaillée disponible.")
            elif ok is True:
                box(answer.get("correct_feedback") or answer.get("explanation") or "Bonne réponse.")
            else:
                box(answer.get("selected_feedback") or "Réponse à corriger manuellement.")
                st.info(answer.get("correct_feedback") or answer.get("explanation") or "Aucune correction automatique disponible.")

            if answer.get("learning_objective"):
                st.write(f"**Objectif pédagogique :** {answer['learning_objective']}")
            if answer.get("cognitive_level"):
                st.write(f"**Compétence cognitive :** {answer['cognitive_level']}")
            if answer.get("competency"):
                st.write(f"**Compétence évaluée :** {answer['competency']}")
            if answer.get("remediation"):
                st.write(f"**Piste de révision :** {answer['remediation']}")

def login_screen() -> None:
    st.title("Plateforme locale de quiz")
    st.caption("Choisis ton espace de connexion.")

    col_learner, col_trainer = st.columns(2)

    with col_learner:
        st.subheader("Accès apprenant")
        st.info("L’apprenant ne voit que son espace de test et ses propres résultats.")

        learner_name = st.text_input("Nom / prénom", key="login_learner_name")
        learner_email = st.text_input("Email ou identifiant", key="login_learner_email")
        learner_group = st.text_input("Groupe / session", key="login_learner_group")
        access_code = st.text_input("Code d’accès", type="password", key="login_learner_code")

        if st.button("Entrer comme apprenant", type="primary", width="stretch"):
            if not learner_name.strip() or not learner_email.strip():
                st.warning("Renseigne le nom et l’email ou identifiant.")
            elif access_code.strip() != LEARNER_ACCESS_CODE:
                st.error("Code d’accès incorrect.")
            else:
                learner = create_or_get_learner(
                    name=learner_name,
                    email=learner_email,
                    group_name=learner_group,
                )
                st.session_state.learner = learner
                st.session_state.role = "learner"
                persist_learner_url_context()
                st.rerun()

    with col_trainer:
        st.subheader("Accès formateur")
        st.info("Le formateur voit la création, l’import, l’historique et les résultats.")

        trainer_password = st.text_input("Mot de passe formateur", type="password", key="login_trainer_password")

        if st.button("Entrer comme formateur", width="stretch"):
            if check_trainer_password(trainer_password):
                st.session_state.role = "trainer"
                st.rerun()
            else:
                st.error("Mot de passe formateur incorrect.")

    st.markdown("---")
    st.warning(
        "Prototype local : cette séparation masque les espaces dans l’interface. "
        "Ce n’est pas encore une authentification web sécurisée de production."
    )
    st.caption("Code apprenant par défaut : CIVIQUE2026 | Mot de passe formateur par défaut : formateur123")


def render_analysis(analysis: Dict[str, Any]) -> None:
    if not analysis:
        st.info("Aucune analyse pédagogique disponible.")
        return

    if analysis.get("error"):
        st.error(analysis.get("error"))
        return

    st.markdown("### Objectif pédagogique détecté")
    st.info(analysis.get("training_goal", ""))

    concepts = analysis.get("key_concepts") or []
    st.markdown("### Notions clés")
    if not concepts:
        st.warning("Aucune notion clé détectée.")
    else:
        for i, concept in enumerate(concepts, start=1):
            with st.expander(f"Notion {i} - {concept.get('concept', '')}", expanded=i <= 3):
                st.write(f"**Définition :** {concept.get('definition', '')}")
                st.write(f"**Importance :** {concept.get('importance', '')}/5")
                st.write(f"**Angle de question :** {concept.get('question_angle', '')}")
                if concept.get("source_excerpt"):
                    st.caption(f"Extrait source : {concept.get('source_excerpt')}")


def render_creator_question(question: Dict[str, Any], index: int) -> None:
    qtype = question.get("type", "")
    score = int(question.get("quality_score") or 0)

    with st.expander(f"Question {index} — {qtype} — score {score}/100 ({quality_label(score)})", expanded=True):
        col_meta1, col_meta2, col_meta3 = st.columns(3)
        col_meta1.markdown(f"**Niveau :** {question.get('difficulty', '')}")
        col_meta2.markdown(f"**Cognitif :** {question.get('cognitive_level', '')}")
        col_meta3.markdown(f"**Domaine :** {question.get('domain', 'Non classé')}")

        st.markdown(f"**Compétence évaluée :** {question.get('competency', '')}")
        st.markdown(f"**Notion évaluée :** {question.get('concept_evaluated', '')}")
        st.markdown(question.get("question", ""))

        pairs = question.get("pairs") or []
        options = question.get("options") or []

        if qtype == "matching" and pairs:
            col_left, col_right = st.columns(2)
            with col_left:
                st.markdown("**Colonne A**")
                for pair_index, pair in enumerate(pairs, start=1):
                    st.write(f"{pair_index}. {pair.get('left', '')}")
            with col_right:
                st.markdown("**Colonne B**")
                for pair_index, pair in enumerate(pairs, start=1):
                    label = chr(64 + pair_index)
                    st.write(f"{label}. {pair.get('right', '')}")

            st.markdown("**Correction**")
            for pair in pairs:
                st.success(f"{pair.get('left', '')} -> {pair.get('right', '')}")
        else:
            feedbacks = question.get("feedbacks") or {}
            for option_index, option in enumerate(options):
                label = chr(65 + option_index)
                st.write(f"{label}. {option}")
                if feedbacks.get(label):
                    st.caption(f"Feedback {label} : {feedbacks[label]}")

            st.success(f"Réponse correcte : {question.get('correct_answer', '')}")

        st.write(f"**Explication :** {question.get('explanation', '')}")
        if question.get("remediation"):
            st.write(f"**Piste de révision :** {question.get('remediation')}")
        if question.get("source_excerpt"):
            st.caption(f"Extrait source : {question.get('source_excerpt')}")


def render_test_question(question: Dict[str, Any], index: int) -> Any:
    qtype = question.get("type", "")
    st.markdown(f"### Question {index}")
    st.markdown(question.get("question", ""))

    options = question.get("options") or []
    pairs = question.get("pairs") or []

    if qtype in ["single_choice", "true_false"]:
        display_options = [f"{option_label(i)}. {option}" for i, option in enumerate(options)]
        selected = st.radio(
            "Choisis une réponse",
            options=display_options,
            key=f"test_answer_{index}",
        )
        if selected:
            return selected.split(".", 1)[0].strip()
        return ""

    if qtype == "matching" and pairs:
        right_options = [p.get("right", "") for p in pairs]
        given = {}
        for pair in pairs:
            left = pair.get("left", "")
            given[left] = st.selectbox(
                f"Associer : {left}",
                options=[""] + right_options,
                key=f"matching_{index}_{left}",
            )
        return given

    if qtype == "short_answer":
        return st.text_area("Ta réponse", key=f"short_answer_{index}", height=120)

    return st.text_input("Ta réponse", key=f"generic_answer_{index}")


def render_session_question(question: Dict[str, Any], index: int, session_id: int) -> Any:
    qtype = question.get("type", "")
    st.markdown(f"### Question {index}")
    st.markdown(question.get("question", ""))

    options = question.get("options") or []
    pairs = question.get("pairs") or []
    prefix = f"session_{session_id}_{index}"

    if qtype in ["single_choice", "true_false"]:
        display_options = [f"{option_label(i)}. {option}" for i, option in enumerate(options)]
        selected = st.radio("Choisis une réponse", options=display_options, key=f"{prefix}_answer")
        if selected:
            return selected.split(".", 1)[0].strip()
        return ""

    if qtype == "matching" and pairs:
        right_options = [p.get("right", "") for p in pairs]
        given = {}
        for pair in pairs:
            left = pair.get("left", "")
            given[left] = st.selectbox(
                f"Associer : {left}",
                options=[""] + right_options,
                key=f"{prefix}_matching_{left}",
            )
        return given

    if qtype == "short_answer":
        return st.text_area("Ta réponse", key=f"{prefix}_short_answer", height=120)

    return st.text_input("Ta réponse", key=f"{prefix}_generic_answer")


def render_session_correction(answer: Dict[str, Any], question: Dict[str, Any]) -> None:
    if not answer:
        return

    if answer.get("is_correct") is True:
        st.success(answer.get("correct_feedback") or question.get("explanation", "") or "Bonne réponse.")
    elif answer.get("is_correct") is False:
        st.error(answer.get("selected_feedback") or "La réponse choisie n'est pas correcte.")
        st.info(answer.get("correct_feedback") or question.get("explanation", "") or "Correction indisponible.")
    else:
        st.warning(answer.get("selected_feedback") or "Réponse enregistrée, à corriger manuellement.")
        st.info(answer.get("correct_feedback") or question.get("explanation", "") or "Correction indisponible.")

def trainer_app() -> None:
    st.title("Espace formateur")
    st.caption("Création, import enrichi, sauvegarde, restitutions, résultats et exports.")

    with st.sidebar:
        st.success("Connecté : formateur")
        st.button("Se déconnecter", on_click=logout, width="stretch")

        st.header("Paramètres créateur")
        provider = st.selectbox("Moteur de génération", ["Mode demo sans IA", "Ollama local"])

        model_name = "gemma3:1b"
        ollama_base_url = "http://localhost:11434"
        if provider == "Ollama local":
            model_name = st.text_input("Modèle Ollama", value="gemma3:1b")
            ollama_base_url = st.text_input("URL Ollama", value="http://localhost:11434")

        difficulty = st.selectbox("Niveau", ["Debutant", "Intermediaire", "Avance"])
        cognitive_focus = st.selectbox(
            "Compétence cognitive visée",
            ["Memorisation", "Comprehension", "Application", "Analyse", "Mixte"],
            index=1,
        )
        number_of_questions = st.slider("Nombre de questions", min_value=3, max_value=30, value=5)
        question_types = st.multiselect(
            "Types de questions",
            [
                "QCM - une seule bonne reponse",
                "Vrai / Faux",
                "Question courte",
                "Rapprochement d'idees",
            ],
            default=["QCM - une seule bonne reponse"],
        )
        audience = st.text_input("Public cible", value="apprenants en formation professionnelle")
        assessment_goal = st.text_area(
            "Objectif pédagogique",
            value="",
            height=100,
            placeholder="Exemple : vérifier que l'apprenant sait appliquer une notion à une situation concrète.",
        )

    tab_input, tab_analysis, tab_quiz, tab_results, tab_history, tab_export, tab_bank, tab_sessions, tab_settings = st.tabs([
        "1. Source",
        "2. Analyse pédagogique",
        "3. Quiz créateur",
        "4. Résultats",
        "5. Historique quiz",
        "6. Export",
        "7. Banque de questions",
        "8. Sessions",
        "Paramètres accès",
    ])

    with tab_input:
        st.subheader("Importer ou coller un support de formation")

        with st.expander("Charger un quiz structuré depuis CSV ou Excel", expanded=True):
            st.markdown(
                "La V8 accepte maintenant les colonnes `domain`, `subdomain`, `learning_objective`, "
                "`feedback_a` à `feedback_d`, `remediation` et `accepted_answers`."
            )

            st.download_button(
                "Télécharger un modèle CSV enrichi",
                data=template_csv_bytes(),
                file_name="modele_import_quiz_enrichi.csv",
                mime="text/csv",
                width="stretch",
            )

            structured_file = st.file_uploader(
                "Fichier CSV ou Excel de questions",
                type=["csv", "xlsx"],
                key="structured_quiz_file",
            )

            if st.button("Charger ce fichier comme quiz", width="stretch"):
                if structured_file is None:
                    st.warning("Ajoute d'abord un fichier CSV ou Excel.")
                else:
                    try:
                        imported_quiz = read_quiz_table(structured_file)
                        st.session_state.quiz = imported_quiz
                        st.session_state.analysis = imported_quiz.get("analysis")
                        st.session_state.last_saved_id = None
                        st.success(
                            f"Quiz importé : {len(imported_quiz.get('questions', []))} question(s)."
                        )
                    except Exception as exc:
                        st.error(f"Import impossible : {exc}")

        uploaded_file = st.file_uploader(
            "Ou importe un support de formation pour générer un quiz",
            type=["txt", "md", "docx", "pdf"],
        )

        uploaded_text = ""
        if uploaded_file is not None:
            try:
                uploaded_text = read_uploaded_file(uploaded_file)
                st.success(f"Fichier importé : {uploaded_file.name}")
            except Exception as exc:
                st.error(str(exc))

        pasted_text = st.text_area(
            "Ou colle ton contenu ici",
            value=uploaded_text or st.session_state.source_text,
            height=260,
            placeholder="Colle ici le contenu de ta formation...",
        )

        source_text = clean_training_text(pasted_text)
        st.session_state.source_text = source_text

        col_a, col_b, col_c = st.columns([1, 1, 2])
        with col_a:
            analyze = st.button("Analyser le support", width="stretch")
        with col_b:
            generate = st.button("Générer le quiz", type="primary", width="stretch")
        with col_c:
            st.info(f"Volume détecté : {len(source_text.split())} mots")

        if analyze:
            if not source_text:
                st.warning("Ajoute d'abord un contenu de formation.")
            else:
                config = build_config(
                    provider, ollama_base_url, model_name, difficulty, question_types,
                    number_of_questions, audience, assessment_goal, cognitive_focus
                )
                with st.spinner("Analyse pédagogique en cours..."):
                    st.session_state.analysis = analyze_training_content(source_text, config)
                st.success("Analyse terminée.")

        if generate:
            st.session_state.last_saved_id = None
            if not source_text:
                st.warning("Ajoute d'abord un contenu de formation.")
            elif not question_types:
                st.warning("Choisis au moins un type de question.")
            else:
                config = build_config(
                    provider, ollama_base_url, model_name, difficulty, question_types,
                    number_of_questions, audience, assessment_goal, cognitive_focus
                )
                with st.spinner("Analyse puis génération du quiz en cours..."):
                    if not st.session_state.analysis or st.session_state.analysis.get("error"):
                        st.session_state.analysis = analyze_training_content(source_text, config)
                    result = orchestrate_quiz_generation(source_text, config, st.session_state.analysis)
                    st.session_state.quiz = result

                if result.get("error"):
                    st.error("La génération a échoué.")
                    st.info(result.get("hint", "Vérifie les paramètres puis réessaie."))
                else:
                    st.success("Quiz généré avec contrôle qualité.")

    with tab_analysis:
        st.subheader("Analyse pédagogique du support")
        render_analysis(st.session_state.analysis)

    with tab_quiz:
        st.subheader("Quiz créateur")
        quiz = st.session_state.quiz

        if not quiz:
            st.info("Aucun quiz généré, importé ou chargé pour le moment.")
        elif quiz.get("error"):
            st.error(quiz.get("error"))
            st.info(quiz.get("hint", ""))
        else:
            st.markdown(f"### {quiz.get('quiz_title', 'Quiz')}")
            if quiz.get("note"):
                st.warning(quiz["note"])

            quality = quiz.get("quality_summary") or {}
            if quality:
                col_q1, col_q2 = st.columns(2)
                with col_q1:
                    st.metric("Score qualité moyen", quality.get("average_score", 0))
                with col_q2:
                    st.metric("Questions sous 70", quality.get("low_quality_count", 0))
                st.info(quality.get("warning", ""))

            with st.expander("Enregistrer ce quiz dans l'historique local", expanded=True):
                default_title = quiz.get("quiz_title", "Quiz sans titre")
                save_title = st.text_input("Titre du quiz", value=default_title, key="save_title")
                save_module = st.text_input("Module / formation", value="", key="save_module")

                if st.button("Enregistrer le quiz", type="primary", width="stretch"):
                    saved_id = save_quiz(
                        quiz=quiz,
                        title=save_title,
                        module=save_module,
                        difficulty=difficulty,
                        source_preview=st.session_state.source_text,
                    )
                    st.session_state.last_saved_id = saved_id
                    st.success(f"Quiz enregistré dans l'historique local. ID : {saved_id}")

                if st.session_state.last_saved_id:
                    st.info(f"Dernière sauvegarde : ID {st.session_state.last_saved_id}")

            questions = quiz.get("questions", [])
            st.markdown(f"### Aperçu des questions ({len(questions)} au total)")
            st.info(
                "Pour éviter de ralentir l'application, seules les premières questions sont affichées. "
                "Le quiz complet est bien enregistré et utilisable côté apprenant."
            )

            max_preview = len(questions)
            default_preview = min(10, max_preview)
            preview_count = st.number_input(
                "Nombre de questions à afficher dans l'aperçu",
                min_value=0,
                max_value=max_preview,
                value=default_preview,
                step=5,
                key="creator_preview_count",
            )

            if preview_count == 0:
                st.caption("Aucune question affichée dans l'aperçu.")
            else:
                for index, question in enumerate(questions[:preview_count], start=1):
                    render_creator_question(question, index)

                if len(questions) > preview_count:
                    st.caption(
                        f"{len(questions) - preview_count} question(s) masquée(s) dans l'aperçu "
                        "pour préserver la fluidité."
                    )

    with tab_results:
        st.subheader("Résultats des apprenants")
        attempts = get_attempts_summary(limit=200)

        if not attempts:
            st.info("Aucun résultat enregistré pour le moment.")
        else:
            labels = [
                f"{attempt['created_at']} | {attempt['learner_name']} | "
                f"{attempt['quiz_title']} | {attempt['percentage']}% | "
                f"niveau conseillé : {attempt.get('recommended_level') or '-'}"
                for attempt in attempts
            ]

            selected_attempt_index = st.selectbox(
                "Choisir une tentative à afficher",
                options=list(range(len(attempts))),
                format_func=lambda i: labels[i],
                key="trainer_result_attempt_select",
            )

            selected_attempt = attempts[selected_attempt_index]
            details = get_attempt_answers(selected_attempt["id"])
            render_attempt_report(selected_attempt, details, show_learner=True)

    with tab_history:
        st.subheader("Historique local des quiz")
        saved_quizzes = list_saved_quizzes()

        if not saved_quizzes:
            st.info("Aucun quiz enregistré pour le moment.")
        else:
            labels = []
            for row in saved_quizzes:
                module = f" | {row['module']}" if row.get("module") else ""
                labels.append(
                    f"#{row['id']} | {row['created_at']} | {row['title']}{module} | {row['question_count']} questions"
                )

            selected_index = st.selectbox(
                "Quiz sauvegardés",
                options=list(range(len(saved_quizzes))),
                format_func=lambda i: labels[i],
            )
            selected = saved_quizzes[selected_index]

            col_load, col_delete = st.columns(2)
            with col_load:
                if st.button("Charger ce quiz", width="stretch"):
                    loaded = load_quiz(selected["id"])
                    if loaded is None:
                        st.error("Quiz introuvable.")
                    else:
                        st.session_state.quiz = loaded
                        st.session_state.analysis = loaded.get("analysis")
                        st.session_state.last_saved_id = selected["id"]
                        st.success("Quiz chargé.")

            with col_delete:
                if st.button("Supprimer ce quiz", width="stretch"):
                    delete_quiz(selected["id"])
                    st.success("Quiz supprimé de l'historique.")
                    st.rerun()

            st.markdown("### Détails")
            st.write(f"**Titre :** {selected['title']}")
            st.write(f"**Module :** {selected.get('module') or '-'}")
            st.write(f"**Niveau :** {selected.get('difficulty') or '-'}")
            st.write(f"**Questions :** {selected['question_count']}")
            st.write(f"**Date :** {selected['created_at']}")

    with tab_export:
        st.subheader("Exporter")
        quiz = st.session_state.quiz

        if not quiz:
            st.info("Génère, importe ou charge d'abord un quiz.")
        elif quiz.get("error"):
            st.warning("Aucun quiz exportable : la génération a échoué.")
        else:
            col1, col2, col3 = st.columns(3)
            with col1:
                st.download_button(
                    "Télécharger JSON",
                    data=quiz_to_json_bytes(quiz),
                    file_name="quiz.json",
                    mime="application/json",
                    width="stretch",
                )
            with col2:
                st.download_button(
                    "Télécharger CSV",
                    data=quiz_to_csv_bytes(quiz),
                    file_name="quiz.csv",
                    mime="text/csv",
                    width="stretch",
                )
            with col3:
                st.download_button(
                    "Télécharger Markdown",
                    data=quiz_to_markdown_bytes(quiz),
                    file_name="quiz.md",
                    mime="text/markdown",
                    width="stretch",
                )

            st.markdown("### Aperçu Markdown")
            st.code(quiz_to_markdown(quiz), language="markdown")


    with tab_bank:
        st.subheader("Banque de questions")
        st.caption("Cette banque sert à constituer des examens aléatoires ou ciblés à partir de toutes les questions validées.")

        current_quiz = st.session_state.quiz
        if current_quiz and not current_quiz.get("error"):
            if st.button("Ajouter le quiz actuellement chargé à la banque", type="primary", width="stretch"):
                result = add_quiz_to_bank(current_quiz, source_quiz_id=st.session_state.last_saved_id)
                st.success(
                    f"Ajout terminé : {result['added']} nouvelle(s) question(s), "
                    f"{result['ignored']} doublon(s) ou question(s) ignorée(s)."
                )
        else:
            st.info("Charge ou importe d'abord un quiz pour pouvoir l'ajouter à la banque.")

        stats = get_question_bank_stats()
        st.metric("Nombre total de questions actives", stats["total"])

        col_stats1, col_stats2, col_stats3 = st.columns(3)
        with col_stats1:
            st.markdown("#### Par domaine")
            st.dataframe(stats["by_domain"], width="stretch", hide_index=True)
        with col_stats2:
            st.markdown("#### Par niveau")
            st.dataframe(stats["by_difficulty"], width="stretch", hide_index=True)
        with col_stats3:
            st.markdown("#### Par type")
            st.dataframe(stats["by_type"], width="stretch", hide_index=True)

        st.markdown("### Créer un quiz depuis la banque")
        bank_domains = ["Tous"] + list_bank_domains()
        bank_difficulties = ["Tous"] + list_bank_difficulties()

        col_b1, col_b2, col_b3 = st.columns(3)
        with col_b1:
            bank_count = st.number_input("Nombre de questions", min_value=1, max_value=200, value=40, step=1)
        with col_b2:
            bank_domain = st.selectbox("Domaine", bank_domains, key="trainer_bank_domain")
        with col_b3:
            bank_difficulty = st.selectbox("Niveau", bank_difficulties, key="trainer_bank_difficulty")

        bank_title = st.text_input(
            "Titre du quiz créé",
            value="Examen généré depuis la banque - 40 questions",
            key="trainer_bank_title",
        )

        auto_save_bank_quiz = st.checkbox(
            "Enregistrer automatiquement ce quiz dans l'historique",
            value=True,
            key="auto_save_bank_quiz",
        )

        if st.button("Créer un examen aléatoire depuis la banque", width="stretch"):
            selected_questions = select_random_questions(
                limit=int(bank_count),
                domain="" if bank_domain == "Tous" else bank_domain,
                difficulty="" if bank_difficulty == "Tous" else bank_difficulty,
            )

            if not selected_questions:
                st.warning("Aucune question disponible avec ces critères.")
            else:
                new_quiz = build_quiz_from_bank(
                    selected_questions,
                    title=bank_title,
                    mode="random",
                )
                st.session_state.quiz = new_quiz
                if auto_save_bank_quiz:
                    saved_id = save_quiz(
                        quiz=new_quiz,
                        title=bank_title,
                        module="Banque de questions",
                        difficulty=bank_difficulty if bank_difficulty != "Tous" else "",
                        source_preview="Quiz généré depuis la banque de questions.",
                    )
                    st.session_state.last_saved_id = saved_id
                    st.success(f"Quiz créé et enregistré. ID : {saved_id}")
                else:
                    st.success("Quiz créé et chargé dans l'onglet Quiz créateur. Tu peux l'enregistrer manuellement.")

        st.info(
            "La sélection adaptative côté apprenant utilise les erreurs précédentes : "
            "elle privilégie les domaines où l'apprenant s'est trompé, puis complète avec des questions aléatoires."
        )


    with tab_sessions:
        st.subheader("Sessions de formation")
        st.caption("Session dirigée : le formateur pilote les questions et voit les réponses en direct.")

        st.markdown("### Créer une session")

        saved_quizzes = list_saved_quizzes()
        source_type = st.radio(
            "Source des questions",
            ["Quiz sauvegardé", "Banque de questions aléatoire"],
            horizontal=True,
            key="session_source_type",
        )

        session_title = st.text_input("Titre de la session", value="Session dirigée - formation", key="session_title")
        session_code = st.text_input(
            "Code session à communiquer",
            value=generate_session_code("SESSION"),
            key="session_code",
        ).upper()

        questions_for_session = []
        source_label = ""

        if source_type == "Quiz sauvegardé":
            if not saved_quizzes:
                st.warning("Aucun quiz sauvegardé disponible.")
            else:
                labels = [f"#{row['id']} | {row['title']} | {row['question_count']} questions" for row in saved_quizzes]
                selected_index = st.selectbox(
                    "Quiz à utiliser",
                    options=list(range(len(saved_quizzes))),
                    format_func=lambda i: labels[i],
                    key="session_saved_quiz_select",
                )
                selected_quiz_row = saved_quizzes[selected_index]
                selected_quiz = load_quiz(selected_quiz_row["id"])
                questions_for_session = selected_quiz.get("questions", []) if selected_quiz else []
                source_label = f"quiz_saved:{selected_quiz_row['id']}"
                st.info(f"{len(questions_for_session)} question(s) disponibles pour cette session.")
        else:
            stats = get_question_bank_stats()
            st.info(f"Banque disponible : {stats['total']} question(s).")
            bank_domains = ["Tous"] + list_bank_domains()
            bank_difficulties = ["Tous"] + list_bank_difficulties()

            col_s1, col_s2, col_s3 = st.columns(3)
            with col_s1:
                session_bank_count = st.number_input("Nombre de questions", min_value=1, max_value=200, value=10, step=1, key="session_bank_count")
            with col_s2:
                session_bank_domain = st.selectbox("Domaine", bank_domains, key="session_bank_domain")
            with col_s3:
                session_bank_difficulty = st.selectbox("Niveau", bank_difficulties, key="session_bank_difficulty")

            if stats["total"] > 0:
                questions_for_session = select_random_questions(
                    limit=int(session_bank_count),
                    domain="" if session_bank_domain == "Tous" else session_bank_domain,
                    difficulty="" if session_bank_difficulty == "Tous" else session_bank_difficulty,
                )
                source_label = "question_bank_random"
                st.info(f"{len(questions_for_session)} question(s) seront sélectionnées.")

        if st.button("Créer la session dirigée", type="primary", width="stretch"):
            if not questions_for_session:
                st.warning("Impossible de créer la session : aucune question disponible.")
            else:
                try:
                    session_id = create_training_session(
                        title=session_title,
                        access_code=session_code,
                        questions=questions_for_session,
                        mode="directed",
                        source=source_label,
                    )
                    st.success(f"Session créée. ID : {session_id} | Code : {session_code}")
                    st.info("Communique ce code aux apprenants, puis clique sur Ouvrir dans le pilotage ci-dessous.")
                except Exception as exc:
                    st.error(f"Création impossible : {exc}")

        st.markdown("---")
        st.markdown("### Piloter une session")

        sessions = list_training_sessions(limit=100)
        if not sessions:
            st.info("Aucune session créée pour le moment.")
        else:
            session_labels = [f"#{row['id']} | {row['access_code']} | {row['title']} | {row['status']}" for row in sessions]
            selected_session_index = st.selectbox(
                "Session",
                options=list(range(len(sessions))),
                format_func=lambda i: session_labels[i],
                key="trainer_session_select",
            )
            session = get_training_session(sessions[selected_session_index]["id"])

            if not session:
                st.error("Session introuvable.")
            else:
                questions = session.get("questions", [])
                current_index = max(0, min(int(session.get("current_question_index") or 0), max(0, len(questions) - 1)))
                current_question_number = current_index + 1 if questions else 0
                current_question = questions[current_index] if questions else {}

                col_meta1, col_meta2, col_meta3, col_meta4 = st.columns(4)
                col_meta1.metric("Statut", session["status"])
                col_meta2.metric("Question", f"{current_question_number} / {len(questions)}")
                col_meta3.metric("Code", session["access_code"])
                col_meta4.metric("Correction", "Visible" if session["show_correction"] else "Masquée")

                control_cols = st.columns(6)
                with control_cols[0]:
                    if st.button("Ouvrir", width="stretch"):
                        update_session_status(session["id"], "live")
                        st.rerun()
                with control_cols[1]:
                    if st.button("Pause", width="stretch"):
                        update_session_status(session["id"], "paused")
                        st.rerun()
                with control_cols[2]:
                    if st.button("Précédente", width="stretch"):
                        update_session_position(session["id"], current_index - 1)
                        set_session_show_correction(session["id"], False)
                        st.rerun()
                with control_cols[3]:
                    if st.button("Suivante", width="stretch"):
                        update_session_position(session["id"], current_index + 1)
                        set_session_show_correction(session["id"], False)
                        st.rerun()
                with control_cols[4]:
                    if st.button("Correction", width="stretch"):
                        set_session_show_correction(session["id"], not session["show_correction"])
                        st.rerun()
                with control_cols[5]:
                    if st.button("Clôturer", width="stretch"):
                        update_session_status(session["id"], "closed")
                        st.rerun()

                if st.button("Actualiser les réponses", width="stretch", key=f"trainer_refresh_session_{session['id']}_{current_question_number}"):
                    st.rerun()

                participants = list_session_participants(session["id"])
                stats = get_session_live_stats(session["id"], current_question_number)

                st.markdown("### Question en cours")
                if current_question:
                    st.write(current_question.get("question", ""))
                    for i, option in enumerate(current_question.get("options") or []):
                        st.write(f"{option_label(i)}. {option}")

                stat_cols = st.columns(4)
                stat_cols[0].metric("Participants", len(participants))
                stat_cols[1].metric("Réponses reçues", stats["answer_count"])
                stat_cols[2].metric("Taux de réponse", f"{stats['percent_answered']}%")
                stat_cols[3].metric("Bonnes réponses", f"{stats['percent_correct']}%")

                st.markdown("#### Répartition des réponses")
                if stats["distribution"]:
                    distribution_rows = [{"Réponse": key, "Nombre": value} for key, value in sorted(stats["distribution"].items())]
                    st.dataframe(distribution_rows, width="stretch", hide_index=True)
                else:
                    st.info("Aucune réponse reçue pour cette question.")

                st.markdown("#### Réponses individuelles")
                if stats["answers"]:
                    answer_rows = []
                    for answer in stats["answers"]:
                        answer_rows.append({
                            "Apprenant": answer.get("learner_name"),
                            "Email": answer.get("learner_email"),
                            "Réponse": answer.get("user_answer_json"),
                            "Correct": answer.get("is_correct"),
                            "Score": answer.get("score"),
                        })
                    st.dataframe(answer_rows, width="stretch", hide_index=True)
                else:
                    st.caption("Aucune réponse individuelle à afficher.")

                st.markdown("### Bilan provisoire par stagiaire")
                summary_rows = get_session_participant_summary(session["id"])
                if summary_rows:
                    st.dataframe(summary_rows, width="stretch", hide_index=True)
                else:
                    st.info("Aucun participant pour le moment.")

    with tab_settings:
        st.subheader("Paramètres d’accès")
        st.write("Ces valeurs peuvent être changées par variables d’environnement avant de lancer Streamlit.")
        st.code(
            '$env:QUIZ_LEARNER_CODE="MONCODE2026"\n'
            '$env:QUIZ_TRAINER_PASSWORD="MonMotDePasseFort"\n'
            'streamlit run app.py',
            language="powershell",
        )
        st.warning("Après modification, relance l’application.")


def learner_app() -> None:
    learner = st.session_state.learner
    st.title("Espace apprenant")

    st.markdown("""
    <div id="v20_4_soft_layout_marker" style="
        padding: 18px 22px;
        border-radius: 18px;
        background: linear-gradient(135deg, #f8fafc 0%, #eef2ff 100%);
        border: 1px solid #e5e7eb;
        margin-bottom: 18px;">
        <h3 style="margin:0 0 8px 0;">Navigation apprenant</h3>
        <p style="margin:0; color:#4b5563;">
            Parcours recommandé : <b>S’entraîner</b> → <b>Examen autonome</b> → <b>Mes résultats</b>.
            La session dirigée reste une option pour les travaux en live.
        </p>
    </div>
    """, unsafe_allow_html=True)

    nav_cols = st.columns(5)
    nav_cols[0].info("S’entraîner\n\nDepuis la banque")
    nav_cols[1].info("Examen autonome\n\nMode cadré")
    nav_cols[2].info("Session autonome\n\nAvec code")
    nav_cols[3].info("Session live\n\nDirigée")
    nav_cols[4].info("Mes résultats\n\nGraphiques conservés")


    with st.sidebar:
        st.success(f"Connecté : {learner['name']}")
        st.caption(learner["email"])
        st.button("Se déconnecter", on_click=logout, width="stretch")

    tab_take, tab_my_results = st.tabs(["Passer un quiz / s’entraîner", "Mes résultats et restitutions"])

    with tab_take:
        st.subheader("Choisir et passer un quiz")

        try:
            from utils.autonomous_v19 import render_v19_autonomous_mode
            render_v19_autonomous_mode(st.session_state.get('learner'))
        except Exception as exc:
            st.error(f'Mode autonome V19 indisponible : {exc}')


        with st.expander("Rejoindre une session dirigée par le formateur", expanded=True):
            st.caption("Utilise ce mode si le formateur pilote les questions en direct.")

            session_code_input = st.text_input("Code session", key="learner_directed_session_code").upper()

            if st.button("Rejoindre la session", type="primary", width="stretch"):
                session = get_training_session_by_code(session_code_input)
                if not session:
                    st.error("Session introuvable. Vérifie le code communiqué par le formateur.")
                elif session["status"] == "closed":
                    st.warning("Cette session est clôturée.")
                else:
                    participant = join_training_session(session["id"], learner["id"])
                    st.session_state.active_directed_session_id = session["id"]
                    st.session_state.active_directed_participant_id = participant["id"]
                    persist_learner_url_context(session.get("access_code", ""))
                    st.success(f"Session rejointe : {session['title']}")

            active_session_id = st.session_state.get("active_directed_session_id")
            active_participant_id = st.session_state.get("active_directed_participant_id")

            if active_session_id and active_participant_id:
                st.caption("Session dirigée : l’actualisation automatique est désactivée par défaut pour éviter de couper la saisie.")

                refresh_col1, refresh_col2 = st.columns([1, 2])
                with refresh_col1:
                    if st.button("Actualiser maintenant", width="stretch", key=f"manual_refresh_directed_session_{active_session_id}"):
                        st.rerun()
                with refresh_col2:
                    auto_refresh = st.checkbox(
                        "Actualisation automatique lente, toutes les 15 secondes",
                        value=False,
                        key=f"auto_refresh_directed_session_{active_session_id}",
                    )

                if False and st_autorefresh is not None:
                    # V20.5 disabled: st_autorefresh removed
                    pass
                elif False and st_autorefresh is None:
                    st.info("Actualisation automatique indisponible : utilise le bouton Actualiser maintenant.")

                session = get_training_session(active_session_id)
                if not session:
                    st.error("Session active introuvable.")
                elif session["status"] == "closed":
                    st.warning("La session est clôturée.")
                elif session["status"] in ["waiting", "paused"]:
                    st.info("La session est en attente ou en pause. Attends que le formateur l'ouvre.")
                else:
                    questions = session.get("questions", [])
                    if not questions:
                        st.warning("Aucune question dans cette session.")
                    else:
                        current_index = max(0, min(int(session.get("current_question_index") or 0), len(questions) - 1))
                        current_question_number = current_index + 1
                        current_question = questions[current_index]

                        existing_answer = get_session_answer(session["id"], active_participant_id, current_question_number)

                        st.markdown("---")
                        st.markdown(f"## Session : {session['title']}")
                        st.caption(f"Question {current_question_number} / {len(questions)}")

                        if existing_answer:
                            st.success("Réponse enregistrée. Attends la correction ou la question suivante du formateur.")
                            if session.get("show_correction"):
                                render_session_correction(existing_answer, current_question)
                            else:
                                st.info("Correction masquée pour le moment.")
                        else:
                            with st.form(f"session_question_form_{session['id']}_{current_question_number}"):
                                user_answer = render_session_question(current_question, current_question_number, session["id"])
                                submitted_session_answer = st.form_submit_button("Valider ma réponse")

                            if submitted_session_answer:
                                evaluation = evaluate_answer(current_question, user_answer)
                                save_session_answer(
                                    session_id=session["id"],
                                    participant_id=active_participant_id,
                                    learner_id=learner["id"],
                                    question_index=current_question_number,
                                    question=current_question,
                                    user_answer=user_answer,
                                    correct_answer=evaluation["correct_answer"],
                                    is_correct=evaluation["is_correct"],
                                    score=evaluation["score"],
                                    selected_feedback=evaluation.get("selected_feedback", ""),
                                    correct_feedback=evaluation.get("correct_feedback", ""),
                                )
                                st.success("Réponse enregistrée. Attends que le formateur affiche la correction ou passe à la question suivante.")
                                st.rerun()

        st.markdown("### Entraînement individuel")


        with st.expander("Démarrer un examen ou entraînement depuis la banque de questions", expanded=True):
            stats = get_question_bank_stats()
            st.caption(f"Banque disponible : {stats['total']} question(s).")

            bank_domains = ["Tous"] + list_bank_domains()
            bank_difficulties = ["Tous"] + list_bank_difficulties()

            col_l1, col_l2, col_l3 = st.columns(3)
            with col_l1:
                learner_bank_mode = st.selectbox(
                    "Mode",
                    ["Aléatoire", "Adaptatif selon mes erreurs"],
                    key="learner_bank_mode",
                )
            with col_l2:
                learner_bank_count = st.number_input(
                    "Nombre de questions",
                    min_value=1,
                    max_value=200,
                    value=40,
                    step=1,
                    key="learner_bank_count",
                )
            with col_l3:
                learner_bank_domain = st.selectbox(
                    "Domaine",
                    bank_domains,
                    key="learner_bank_domain",
                )

            learner_bank_difficulty = st.selectbox(
                "Niveau",
                bank_difficulties,
                key="learner_bank_difficulty",
            )

            if st.button("Démarrer depuis la banque", type="primary", width="stretch"):
                domain_filter = "" if learner_bank_domain == "Tous" else learner_bank_domain
                difficulty_filter = "" if learner_bank_difficulty == "Tous" else learner_bank_difficulty

                if learner_bank_mode == "Adaptatif selon mes erreurs":
                    selected_questions = select_adaptive_questions(
                        learner_email=learner["email"],
                        limit=int(learner_bank_count),
                        domain=domain_filter,
                        difficulty=difficulty_filter,
                    )
                    mode_key = "adaptive"
                    title = f"Entraînement adaptatif - {int(learner_bank_count)} questions"
                else:
                    selected_questions = select_random_questions(
                        limit=int(learner_bank_count),
                        domain=domain_filter,
                        difficulty=difficulty_filter,
                    )
                    mode_key = "random"
                    title = f"Examen aléatoire - {int(learner_bank_count)} questions"

                if not selected_questions:
                    st.warning("Aucune question disponible dans la banque avec ces critères.")
                else:
                    active_quiz = build_quiz_from_bank(
                        selected_questions,
                        title=title,
                        mode=mode_key,
                        learner_email=learner["email"],
                    )
                    attempt_id = start_attempt(
                        learner_id=learner["id"],
                        quiz_id=None,
                        quiz_title=title,
                    )
                    st.session_state.active_attempt_id = attempt_id
                    st.session_state.active_quiz_for_test = active_quiz
                    st.session_state.last_completed_attempt_id = None
                    st.success("Quiz démarré depuis la banque. Réponds aux questions ci-dessous.")

        st.markdown("### Ou choisir un quiz sauvegardé")

        saved_quizzes = list_saved_quizzes()
        if not saved_quizzes:
            st.warning("Aucun quiz disponible pour le moment.")
            return

        labels = []
        for row in saved_quizzes:
            module = f" | {row['module']}" if row.get("module") else ""
            labels.append(f"#{row['id']} | {row['title']}{module} | {row['question_count']} questions")

        selected_index = st.selectbox(
            "Quiz disponible",
            options=list(range(len(saved_quizzes))),
            format_func=lambda i: labels[i],
            key="learner_quiz_select",
        )
        selected = saved_quizzes[selected_index]

        if st.button("Démarrer ce quiz", type="primary", width="stretch"):
            loaded_quiz = load_quiz(selected["id"])
            if loaded_quiz is None:
                st.error("Quiz introuvable.")
            else:
                attempt_id = start_attempt(
                    learner_id=learner["id"],
                    quiz_id=selected["id"],
                    quiz_title=selected["title"],
                )
                st.session_state.active_attempt_id = attempt_id
                st.session_state.active_quiz_for_test = loaded_quiz
                st.session_state.last_completed_attempt_id = None
                st.success("Quiz démarré. Réponds aux questions ci-dessous.")

        active_quiz = st.session_state.active_quiz_for_test
        attempt_id = st.session_state.active_attempt_id

        if active_quiz and attempt_id:
            st.markdown("---")
            st.markdown(f"## Quiz en cours : {active_quiz.get('quiz_title', 'Quiz')}")
            questions = active_quiz.get("questions", [])

            with st.form("take_quiz_form"):
                answers = {}
                for i, question in enumerate(questions, start=1):
                    answers[i] = render_test_question(question, i)
                    st.markdown("---")

                submitted = st.form_submit_button("Valider mes réponses")

            if submitted:
                total_score = 0.0
                max_score = 0.0
                manual_count = 0

                for i, question in enumerate(questions, start=1):
                    user_answer = answers.get(i)
                    evaluation = evaluate_answer(question, user_answer)

                    is_correct = evaluation["is_correct"]
                    score = evaluation["score"]

                    if is_correct is None:
                        manual_count += 1
                    else:
                        max_score += 1.0
                        total_score += score

                    save_attempt_result(
                        attempt_id=attempt_id,
                        question_index=i,
                        question=question,
                        user_answer=user_answer,
                        correct_answer=evaluation["correct_answer"],
                        is_correct=is_correct,
                        score=score,
                        selected_feedback=evaluation.get("selected_feedback", ""),
                        correct_feedback=evaluation.get("correct_feedback", ""),
                    )

                percentage = round((total_score / max_score) * 100, 1) if max_score else 0.0
                recommended_level = recommendation_from_percentage(percentage)
                finish_attempt(
                    attempt_id=attempt_id,
                    score=total_score,
                    max_score=max_score,
                    percentage=percentage,
                    recommended_level=recommended_level,
                    manual_count=manual_count,
                )

                st.session_state.last_completed_attempt_id = attempt_id
                st.session_state.active_attempt_id = None
                st.session_state.active_quiz_for_test = None

                st.success("Quiz terminé. Voici ta restitution.")
                current_attempt = get_attempts_for_learner_email(learner["email"], limit=1)[0]
                details = get_attempt_answers(attempt_id)
                render_attempt_report(current_attempt, details, show_learner=False)

    with tab_my_results:
        st.subheader("Mes résultats")
        attempts = get_attempts_for_learner_email(learner["email"], limit=100)

        if not attempts:
            st.info("Aucun résultat enregistré pour ce profil.")
        else:
            labels = [
                f"{attempt['created_at']} | {attempt['quiz_title']} | "
                f"{attempt['percentage']}% | niveau conseillé : {attempt.get('recommended_level') or '-'}"
                for attempt in attempts
            ]

            selected_attempt_index = st.selectbox(
                "Choisir une tentative à afficher",
                options=list(range(len(attempts))),
                format_func=lambda i: labels[i],
                key="learner_result_attempt_select",
            )

            selected_attempt = attempts[selected_attempt_index]
            details = get_attempt_answers(selected_attempt["id"])
            render_attempt_report(selected_attempt, details, show_learner=False)


if st.session_state.role is None:
    login_screen()
    st.stop()

if st.session_state.role == "trainer":
    trainer_app()
elif st.session_state.role == "learner":
    learner_app()
else:
    logout()
