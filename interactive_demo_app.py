"""Standalone trainer preview for Quiz Formation V24.

Deploy this Streamlit entry point separately for demonstrations.
No connection to SQLite, Supabase or trainer credentials is required.
"""
from __future__ import annotations

import hashlib
import json

import streamlit as st

from utils.interactive_activities import (
    can_render_matching,
    can_render_ordering,
    render_matching_cards,
    render_ordering_cards,
)
from utils.interactive_templates import (
    example_rows,
    interactive_csv_bytes,
    interactive_xlsx_bytes,
)
from utils.interactive_lot2 import (
    can_render_word_bank,
    is_complete_decision,
    normalize_word,
    parse_word_bank,
    render_point_budget,
    render_priority_cards,
    render_word_bank_tokens,
)
from utils.table_import import read_quiz_table, rows_to_quiz, validate_imported_quiz


st.set_page_config(
    page_title="Ateliers interactifs V24 — Démonstration",
    page_icon="🎓",
    layout="wide",
)
st.markdown(
    """
    <style>
    .stApp { background: #fbfaf4; }
    h1, h2, h3 { color: #06472f; }
    [data-testid="stSidebar"] { background: #eaf3ec; }
    </style>
    """,
    unsafe_allow_html=True,
)
st.title("Quiz Formation — ateliers interactifs V24")
st.caption(
    "Démonstration indépendante. Aucun quiz, résultat ou fichier n'est enregistré "
    "dans une base de données."
)

with st.sidebar:
    st.subheader("Choisir une source")
    source = st.radio(
        "Exercices à afficher", ["Neuf exemples inclus", "Mon fichier CSV / Excel"]
    )
    st.divider()
    st.download_button(
        "Modèle Excel à compléter",
        data=interactive_xlsx_bytes(),
        file_name="modele_ateliers_interactifs_lots_1_2.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    st.download_button(
        "Modèle CSV à compléter",
        data=interactive_csv_bytes(),
        file_name="modele_ateliers_interactifs_lots_1_2.csv",
        mime="text/csv",
    )

quiz = rows_to_quiz(example_rows(), "exemples_cartes.xlsx")
if source == "Mon fichier CSV / Excel":
    uploaded = st.file_uploader("Choisis ton fichier", type=["xlsx", "csv"])
    if uploaded is not None:
        try:
            quiz = read_quiz_table(uploaded)
        except Exception as exc:
            st.error(f"Impossible de lire ce fichier : {exc}")
            st.stop()
        report = validate_imported_quiz(quiz)
        if report["errors"]:
            st.error(
                f"{len(report['errors'])} erreur(s) dans ton fichier. "
                "Corrige les lignes avant la démonstration."
            )
            for message in report["errors"]:
                st.write(f"- {message}")
            st.stop()
        if report["warnings"]:
            st.warning(f"{len(report['warnings'])} avertissement(s) d'import.")
        st.success(
            f"{len(quiz.get('questions') or [])} question(s) contrôlée(s). "
            "Le fichier n'a pas été ajouté à la banque."
        )

candidates = []
for index, question in enumerate(quiz.get("questions") or []):
    if (
        question.get("type") == "ordering"
        and can_render_ordering(question.get("items") or [])
    ) or (
        question.get("type") == "matching"
        and can_render_matching(question.get("pairs") or [])
    ) or (
        question.get("type") in {"priority_ranking", "point_allocation"}
        and len(question.get("items") or []) >= 2
    ) or (
        question.get("type") == "fill_blank"
        and can_render_word_bank(
            question,
            len(__import__("re").findall(r"\[\s*(?:\.\.\.|…+)\s*\]", question.get("question") or "")),
        )
    ):
        candidates.append((index, question))

if not candidates:
    st.warning(
        "Aucun atelier interactif exploitable n'a été trouvé."
    )
    st.stop()

choices = [i for i, _ in candidates]
selected = st.selectbox(
    "Sélectionner une question à tester",
    choices,
    format_func=lambda i: (
        f"Q{i + 1} · {quiz['questions'][i].get('domain')} "
        f"· {quiz['questions'][i].get('question')}"
    ),
)
question = quiz["questions"][selected]
fingerprint = hashlib.sha256(
    json.dumps(question, sort_keys=True, ensure_ascii=False).encode("utf-8")
).hexdigest()[:12]
key = f"demo_{selected}_{fingerprint}"

st.subheader("Vue apprenti")
st.markdown(f"**{question.get('question') or ''}**")
st.caption(
    f"Formation : {question.get('training_scope') or '-'} · "
    f"Domaine : {question.get('domain') or '-'} · "
    f"Sous-domaine : {question.get('subdomain') or '-'}"
)
context = question.get("context")
if isinstance(context, dict) and context.get("text"):
    with st.expander(context.get("title") or "Cas pratique"):
        st.write(context["text"])

if question["type"] == "ordering":
    items = question.get("items") or []
    answer = render_ordering_cards(items, key + "_cards")
    complete = len(answer) == len(items)
    correct_order = question.get("correct_order") or []
    expected = [
        str(item).upper() for item in correct_order
    ] if isinstance(correct_order, list) else list(str(correct_order).upper())
    score = sum(1 for i, x in enumerate(expected) if i < len(answer) and answer[i] == x)
    denominator = len(expected)
    by_label = {str(item["label"]).upper(): item["text"] for item in items}
    correction_text = " → ".join(by_label.get(item, item) for item in expected)
elif question["type"] == "matching":
    pairs = question.get("pairs") or []
    answer = render_matching_cards(pairs, key + "_cards")
    complete = len(answer) == len(pairs)
    expected_pairs = {str(p["left"]): str(p["right"]) for p in pairs}
    score = sum(1 for left, right in expected_pairs.items() if answer.get(left) == right)
    denominator = len(pairs)
    correction_text = "\n".join(f"- {left} → {right}" for left, right in expected_pairs.items())
elif question["type"] == "priority_ranking":
    answer = render_priority_cards(question, question["items"], key + "_priority")
    complete = is_complete_decision(question, answer)
    score, denominator = None, 0
    correction_text = "Priorisation à analyser avec les critères du formateur."
elif question["type"] == "point_allocation":
    answer = render_point_budget(question, question["items"], key + "_budget")
    complete = is_complete_decision(question, answer)
    score, denominator = None, 0
    correction_text = "Arbitrage à analyser avec les critères du formateur."
else:
    words = parse_word_bank(question.get("word_bank"))
    expected = parse_word_bank(question.get("correct_answers"))
    answer = render_word_bank_tokens(words, len(expected), key + "_words")
    complete = is_complete_decision(question, answer)
    score = sum(
        normalize_word(answer.get(str(i), "")) == normalize_word(word)
        for i, word in enumerate(expected, start=1)
    )
    denominator = len(expected)
    correction_text = "Réponses attendues : " + ", ".join(expected)

if not complete:
    st.info("Complète l'exercice avant de valider.")

if st.button("Valider cet essai et afficher la correction", disabled=not complete, type="primary"):
    st.session_state[key + "_validated_answer"] = answer

if st.session_state.get(key + "_validated_answer") == answer and complete:
    if score is None:
        st.info("Réponse enregistrée dans cet essai — correction différée.")
        if question.get("evaluation_criteria"):
            st.write("Critères : " + " ; ".join(question["evaluation_criteria"]))
    else:
        st.metric("Score de l'essai", f"{score} / {denominator}")
    st.markdown("**Correction attendue ou piste de correction**")
    st.markdown(correction_text)
    if question.get("explanation"):
        st.info(question["explanation"])
    if question.get("remediation"):
        st.caption(f"Piste de révision : {question['remediation']}")

st.divider()
st.caption(
    "Cette démonstration ne contacte pas Supabase et ne remplace pas "
    "l'espace formateur de l'application V23. L'import dans la banque "
    "se fait ensuite dans 1. Source de l'application principale."
)
