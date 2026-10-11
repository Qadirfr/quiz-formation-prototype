from __future__ import annotations

import csv
import io
import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List


TYPE_MAP = {
    "qcm": "single_choice",
    "choix_unique": "single_choice",
    "single_choice": "single_choice",
    "multiple_choice": "single_choice",
    "vrai_faux": "true_false",
    "true_false": "true_false",
    "question_courte": "short_answer",
    "short_answer": "short_answer",
    "rapprochement": "matching",
    "rapprochement_idees": "matching",
    "appariement": "matching",
    "matching": "matching",
    "ordering": "ordering",
    "order": "ordering",
    "ordonnancement": "ordering",
    "ordre": "ordering",
    "classement": "ordering",
    "sequence": "ordering",
    "sequencing": "ordering",
    "ranking": "ordering",
    "self_assessment": "self_assessment",
    "self_evaluation": "self_assessment",
    "auto_evaluation": "self_assessment",
    "autoevaluation": "self_assessment",
    "likert": "self_assessment",
    "rating_scale": "self_assessment",
    "scale": "self_assessment",
    "fill_blank": "fill_blank",
    "fill_in_blank": "fill_blank",
    "fill_in_the_blank": "fill_blank",
    "texte_a_trous": "fill_blank",
    "question_a_trous": "fill_blank",
    "cloze": "fill_blank",
    "completion": "fill_blank",
    "point_allocation": "point_allocation",
    "allocation_points": "point_allocation",
    "priority_ranking": "priority_ranking",
    "prioritization": "priority_ranking",
    "priorisation": "priority_ranking",
    "long_answer": "long_answer",
    "essay": "long_answer",
    "essay_response": "long_answer",
    "open_answer": "long_answer",
}


def normalize_header(value: Any) -> str:
    text = "" if value is None else str(value).strip()
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9]+", "_", text)
    return text.strip("_").lower()


def clean_cell(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def get_value(row: Dict[str, Any], *names: str) -> str:
    for name in names:
        key = normalize_header(name)
        value = clean_cell(row.get(key, ""))
        if value:
            return value
    return ""


def parse_int(value: Any, default: int = 80) -> int:
    try:
        return int(float(str(value).strip()))
    except Exception:
        return default


def parse_bool(value: Any, default: bool = False) -> bool:
    text = normalize_header(value)
    if not text:
        return default
    if text in {"1", "true", "vrai", "oui", "yes", "y"}:
        return True
    if text in {"0", "false", "faux", "non", "no", "n"}:
        return False
    return default


def normalize_type(value: str) -> str:
    key = normalize_header(value)
    return TYPE_MAP.get(key, key or "single_choice")


def read_csv_rows(uploaded_file) -> List[Dict[str, Any]]:
    raw = uploaded_file.getvalue()

    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")

    first_line = text.splitlines()[0] if text.splitlines() else ""
    try:
        dialect = csv.Sniffer().sniff(text[:2048], delimiters=";,")
        delimiter = dialect.delimiter
    except Exception:
        delimiter = ";" if ";" in first_line else ","

    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    rows = []
    for row in reader:
        clean_row = {normalize_header(k): clean_cell(v) for k, v in row.items() if k is not None}
        rows.append(clean_row)
    return rows


def read_xlsx_rows(uploaded_file) -> List[Dict[str, Any]]:
    try:
        from openpyxl import load_workbook
    except ImportError as exc:
        raise RuntimeError("Le module openpyxl est manquant. Lance : pip install openpyxl") from exc

    uploaded_file.seek(0)
    wb = load_workbook(uploaded_file, data_only=True)
    ws = wb.active

    values = list(ws.iter_rows(values_only=True))
    if not values:
        return []

    headers = [normalize_header(v) for v in values[0]]
    rows = []

    for line in values[1:]:
        if not any(clean_cell(v) for v in line):
            continue
        row = {}
        for header, value in zip(headers, line):
            if header:
                row[header] = clean_cell(value)
        rows.append(row)

    return rows


def read_json_quiz(uploaded_file) -> Dict[str, Any]:
    raw = uploaded_file.getvalue()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")

    try:
        payload = json.loads(text)
    except Exception as exc:
        raise ValueError(f"JSON invalide : {exc}") from exc

    if isinstance(payload, list):
        payload = {
            "quiz_title": f"Quiz importe - {Path(uploaded_file.name).stem}",
            "questions": payload,
        }

    if not isinstance(payload, dict):
        raise ValueError(
            "Le JSON doit contenir un objet quiz ou une liste de questions."
        )

    questions = payload.get("questions")
    if not isinstance(questions, list) or not questions:
        raise ValueError(
            "Le JSON doit contenir une liste non vide dans la cle 'questions'."
        )

    normalized_questions: List[Dict[str, Any]] = []
    for index, raw_question in enumerate(questions, start=1):
        if not isinstance(raw_question, dict):
            raise ValueError(
                f"Question {index} invalide : chaque question doit etre un objet JSON."
            )

        question = dict(raw_question)
        question["type"] = normalize_type(
            question.get("type")
            or question.get("question_type")
            or "single_choice"
        )
        question["question"] = clean_cell(
            question.get("question")
            or question.get("question_text")
            or question.get("consigne")
            or question.get("enonce")
        )
        question.setdefault("domain", question.get("domaine") or "Non classe")
        question.setdefault("subdomain", question.get("sous_domaine") or "")
        question.setdefault("difficulty", question.get("niveau") or "Import")
        question.setdefault(
            "cognitive_level",
            question.get("niveau_cognitif") or "",
        )
        question.setdefault(
            "learning_objective",
            question.get("objectif_pedagogique") or "",
        )
        question.setdefault(
            "competency",
            question.get("competence") or question.get("competence_evaluee") or "",
        )
        question.setdefault(
            "concept_evaluated",
            question.get("notion") or question.get("notion_evaluee") or "",
        )
        question.setdefault("options", [])
        question.setdefault("pairs", [])
        question.setdefault("accepted_answers", [])
        question.setdefault("feedbacks", {})
        question.setdefault("explanation", "")
        question.setdefault("remediation", "")
        question.setdefault("source_excerpt", "")
        question.setdefault("quality_score", 80)
        question.setdefault(
            "quality_notes",
            "Question importee depuis un fichier JSON structure.",
        )

        if question["type"] == "true_false" and not question.get("options"):
            question["options"] = ["Vrai", "Faux"]

        normalized_questions.append(question)

    quiz = dict(payload)
    quiz["quiz_title"] = clean_cell(
        quiz.get("quiz_title")
        or quiz.get("title")
        or f"Quiz importe - {Path(uploaded_file.name).stem}"
    )
    quiz["questions"] = normalized_questions
    quiz["analysis_summary"] = quiz.get(
        "analysis_summary",
        "Quiz importe depuis un fichier JSON structure.",
    )
    quiz["quality_summary"] = build_quality_summary(normalized_questions)
    quiz["note"] = quiz.get(
        "note",
        "Quiz charge depuis un fichier JSON. Validation recommandee avant ajout a la banque.",
    )
    return quiz


def parse_items(row: Dict[str, Any]) -> List[Dict[str, str]]:
    items_json = get_value(row, "items_json", "elements_json", "items")
    if items_json:
        try:
            parsed = json.loads(items_json)
            if isinstance(parsed, list):
                items: List[Dict[str, str]] = []
                for index, item in enumerate(parsed):
                    if isinstance(item, dict):
                        label = clean_cell(item.get("label")) or chr(65 + index)
                        text = clean_cell(
                            item.get("text")
                            or item.get("value")
                            or item.get("label_text")
                        )
                    else:
                        label = chr(65 + index)
                        text = clean_cell(item)
                    if text:
                        items.append({"label": label.upper(), "text": text})
                if items:
                    return items
        except Exception:
            pass

    items = []
    for i in range(1, 11):
        text = get_value(
            row,
            f"item_{i}",
            f"element_{i}",
            f"critere_{i}",
        )
        if text:
            items.append({
                "label": chr(64 + i),
                "text": text,
            })
    return items


def parse_pairs(row: Dict[str, Any]) -> List[Dict[str, str]]:
    pairs = []

    pairs_json = get_value(row, "pairs_json", "paires_json")
    if pairs_json:
        try:
            parsed = json.loads(pairs_json)
            if isinstance(parsed, list):
                for item in parsed:
                    if isinstance(item, dict):
                        left = clean_cell(item.get("left", ""))
                        right = clean_cell(item.get("right", ""))
                        if left or right:
                            pairs.append({"left": left, "right": right})
            if pairs:
                return pairs
        except Exception:
            pass

    for i in range(1, 7):
        left = get_value(
            row,
            f"pair_{i}_left",
            f"paire_{i}_gauche",
            f"left_{i}",
            f"gauche_{i}",
        )
        right = get_value(
            row,
            f"pair_{i}_right",
            f"paire_{i}_droite",
            f"right_{i}",
            f"droite_{i}",
        )
        if left or right:
            pairs.append({"left": left, "right": right})

    return pairs


def parse_feedbacks(row: Dict[str, Any]) -> Dict[str, str]:
    feedbacks = {}
    for letter in ["a", "b", "c", "d", "e", "f"]:
        feedback = get_value(
            row,
            f"feedback_{letter}",
            f"explication_{letter}",
            f"retour_{letter}",
        )
        if feedback:
            feedbacks[letter.upper()] = feedback

    true_feedback = get_value(row, "feedback_vrai", "explication_vrai")
    false_feedback = get_value(row, "feedback_faux", "explication_faux")
    if true_feedback:
        feedbacks["VRAI"] = true_feedback
    if false_feedback:
        feedbacks["FAUX"] = false_feedback

    return feedbacks


def build_quality_summary(questions: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not questions:
        return {
            "average_score": 0,
            "low_quality_count": 0,
            "warning": "Aucune question importee.",
        }

    scores = [parse_int(q.get("quality_score", 80), 80) for q in questions]
    average = round(sum(scores) / len(scores), 1)
    low = len([s for s in scores if s < 70])

    return {
        "average_score": average,
        "low_quality_count": low,
        "warning": "Synthese calculee a partir du fichier importe.",
    }


def rows_to_quiz(rows: List[Dict[str, Any]], filename: str = "quiz") -> Dict[str, Any]:
    if not rows:
        raise ValueError("Le fichier ne contient aucune ligne exploitable.")

    title = ""
    for row in rows:
        title = get_value(row, "quiz_title", "titre_quiz", "titre")
        if title:
            break

    if not title:
        title = f"Quiz importe - {Path(filename).stem}"

    questions = []

    for row in rows:
        question_text = get_value(row, "question", "consigne", "enonce")
        if not question_text:
            continue

        qtype = normalize_type(get_value(row, "type", "question_type", "type_question"))

        options = []
        for letter in ["a", "b", "c", "d", "e", "f"]:
            option = get_value(row, f"option_{letter}", f"reponse_{letter}")
            if option:
                options.append(option)

        if qtype == "true_false" and not options:
            options = ["Vrai", "Faux"]

        pairs = parse_pairs(row)
        feedbacks = parse_feedbacks(row)

        correct_answer = get_value(
            row,
            "correct_answer",
            "reponse_correcte",
            "bonne_reponse",
            "correction",
        )

        if qtype == "matching" and not correct_answer:
            correct_answer = "Voir les paires de correction."

        accepted_answers_raw = get_value(
            row,
            "accepted_answers",
            "reponses_acceptees",
            "synonymes",
        )
        accepted_answers = [
            item.strip()
            for item in re.split(r"[|;]", accepted_answers_raw)
            if item.strip()
        ]

        question = {
            "type": qtype,
            "domain": get_value(row, "domain", "domaine") or "Non classe",
            "subdomain": get_value(row, "subdomain", "sous_domaine"),
            "learning_objective": get_value(row, "learning_objective", "objectif_pedagogique"),
            "difficulty": get_value(row, "difficulty", "niveau") or "Import",
            "cognitive_level": get_value(row, "cognitive_level", "niveau_cognitif"),
            "competency": get_value(row, "competency", "competence", "competence_evaluee"),
            "concept_evaluated": get_value(row, "concept_evaluated", "notion", "notion_evaluee"),
            "question": question_text,
            "options": options,
            "pairs": pairs,
            "correct_answer": correct_answer,
            "accepted_answers": accepted_answers,
            "feedbacks": feedbacks,
            "explanation": get_value(row, "explanation", "explication", "justification"),
            "source_excerpt": get_value(row, "source_excerpt", "extrait_source"),
            "remediation": get_value(row, "remediation", "piste_de_revision", "pistes_de_travail"),
            "quality_score": parse_int(get_value(row, "quality_score", "score_qualite"), 80),
            "quality_notes": get_value(row, "quality_notes", "notes_qualite") or "Question importee depuis un fichier structure.",
            "training_scope": get_value(row, "training_scope", "formation"),
            "question_set_type": get_value(
                row,
                "question_set_type",
                "type_serie",
                "assessment_type",
            ),
        }

        items = parse_items(row)
        if items:
            question["items"] = items

        context_text = get_value(
            row,
            "context_text",
            "case_context",
            "case_text",
            "cas_pratique",
            "contexte",
        )
        if context_text:
            question["context"] = {
                "title": get_value(
                    row,
                    "context_title",
                    "case_title",
                    "titre_cas",
                ) or "Cas pratique / contexte",
                "text": context_text,
                "collapsible": parse_bool(
                    get_value(
                        row,
                        "context_collapsible",
                        "case_collapsible",
                    ),
                    True,
                ),
                "expanded": parse_bool(
                    get_value(
                        row,
                        "context_expanded",
                        "case_expanded",
                    ),
                    False,
                ),
            }

        media_url = get_value(
            row,
            "media_url",
            "image_url",
            "illustration_url",
        )
        if media_url:
            question["media"] = {
                "type": get_value(row, "media_type", "type_media") or "image",
                "url": media_url,
                "caption": get_value(
                    row,
                    "media_caption",
                    "image_caption",
                    "legende_media",
                ),
                "alt_text": get_value(
                    row,
                    "media_alt_text",
                    "image_alt_text",
                    "texte_alternatif",
                ),
            }

        total_points = get_value(row, "total_points", "points_total")
        if total_points:
            question["total_points"] = parse_int(total_points, 0)

        ranking_mode = get_value(row, "ranking_mode", "mode_priorisation")
        if ranking_mode:
            question["ranking_mode"] = normalize_header(ranking_mode)

        top_n = get_value(row, "top_n", "nombre_priorites")
        if top_n:
            question["top_n"] = parse_int(top_n, 0)

        correct_order = get_value(
            row,
            "correct_order",
            "expected_order",
            "ordre_correct",
        )
        if correct_order:
            question["correct_order"] = [
                ch for ch in correct_order.upper() if ch.isalpha()
            ]

        scale_min = get_value(row, "scale_min", "echelle_min")
        scale_max = get_value(row, "scale_max", "echelle_max")
        if scale_min:
            question["scale_min"] = parse_int(scale_min, 1)
        if scale_max:
            question["scale_max"] = parse_int(scale_max, 5)

        require_justification = get_value(
            row,
            "require_justification",
            "justification_requise",
        )
        if require_justification:
            question["require_justification"] = parse_bool(
                require_justification,
                True,
            )

        max_words = get_value(row, "max_words", "nombre_mots_max")
        if max_words:
            question["max_words"] = parse_int(max_words, 0)

        max_points = get_value(row, "max_points", "bareme_max")
        if max_points:
            try:
                question["max_points"] = float(str(max_points).replace(",", "."))
            except Exception:
                pass

        criteria_raw = get_value(
            row,
            "evaluation_criteria",
            "grading_criteria",
            "criteres_evaluation",
        )
        if criteria_raw:
            question["evaluation_criteria"] = [
                item.strip()
                for item in re.split(r"[|;]", criteria_raw)
                if item.strip()
            ]

        questions.append(question)

    if not questions:
        raise ValueError("Aucune question n'a ete trouvee. Verifie la colonne 'question'.")

    return {
        "quiz_title": title,
        "analysis_summary": "Quiz importe depuis un fichier CSV ou Excel structure.",
        "questions": questions,
        "quality_summary": build_quality_summary(questions),
        "note": "Quiz charge depuis un fichier. La mise en forme, l'historique, la passation et les restitutions sont disponibles.",
    }


def read_quiz_table(uploaded_file) -> Dict[str, Any]:
    name = uploaded_file.name.lower()

    if name.endswith(".json"):
        return read_json_quiz(uploaded_file)
    if name.endswith(".csv"):
        rows = read_csv_rows(uploaded_file)
    elif name.endswith(".xlsx"):
        rows = read_xlsx_rows(uploaded_file)
    else:
        raise ValueError("Format non supporte. Utilise CSV, XLSX ou JSON.")

    return rows_to_quiz(rows, uploaded_file.name)


def validate_imported_quiz(quiz: Dict[str, Any]) -> Dict[str, Any]:
    from utils.question_schema import classify_question

    errors: List[str] = []
    warnings: List[str] = []
    question_reports: List[Dict[str, Any]] = []

    if not isinstance(quiz, dict):
        return {
            "valid": False,
            "errors": ["Le contenu importe n'est pas un quiz valide."],
            "warnings": [],
            "questions": [],
            "question_count": 0,
        }

    questions = quiz.get("questions") or []
    if not isinstance(questions, list) or not questions:
        errors.append("Le quiz ne contient aucune question exploitable.")
        questions = []

    for index, question in enumerate(questions, start=1):
        q_errors: List[str] = []
        q_warnings: List[str] = []

        if not isinstance(question, dict):
            q_errors.append("La question n'est pas un objet structure.")
            question_reports.append({
                "index": index,
                "type": "unknown",
                "errors": q_errors,
                "warnings": q_warnings,
            })
            continue

        qtype = normalize_type(question.get("type", ""))
        text = clean_cell(question.get("question"))
        if not text:
            q_errors.append("Enonce manquant.")

        if qtype not in set(TYPE_MAP.values()):
            q_errors.append(f"Type non supporte : {qtype}")

        options = question.get("options") or []
        pairs = question.get("pairs") or []
        items = question.get("items") or []

        if qtype == "single_choice":
            if len(options) < 2:
                q_errors.append("QCM : au moins deux options sont requises.")
            if not question.get("correct_answer"):
                q_errors.append("QCM : bonne reponse manquante.")

        elif qtype == "true_false":
            if not question.get("correct_answer"):
                q_errors.append("Vrai/Faux : bonne reponse manquante.")

        elif qtype == "matching":
            if not pairs:
                q_errors.append("Appariement : paires manquantes.")

        elif qtype == "ordering":
            if not items and not options:
                q_errors.append("Ordonnancement : elements a classer manquants.")
            if not (
                question.get("correct_order")
                or question.get("expected_order")
                or question.get("correct_answer")
            ):
                q_warnings.append(
                    "Ordonnancement : ordre attendu absent, correction differee probable."
                )

        elif qtype == "fill_blank":
            blanks = len(re.findall(r"\[\s*(?:\.\.\.|…+)\s*\]", text))
            answers = question.get("correct_answers") or []
            if blanks == 0:
                q_errors.append("Question a trous : aucun marqueur [...] detecte.")
            if answers and blanks and len(answers) != blanks:
                q_errors.append(
                    f"Question a trous : {blanks} trou(s), {len(answers)} reponse(s)."
                )
            if not answers:
                q_errors.append("Question a trous : reponses attendues manquantes.")

        elif qtype == "self_assessment":
            if not items and not options:
                q_errors.append("Auto-positionnement : dimensions manquantes.")

        elif qtype == "point_allocation":
            if not items:
                q_errors.append("Repartition de points : elements manquants.")
            if not question.get("total_points"):
                q_errors.append("Repartition de points : total_points manquant.")

        elif qtype == "priority_ranking":
            if not items:
                q_errors.append("Priorisation : elements manquants.")
            if question.get("ranking_mode") not in {"rank_all", "top_n"}:
                q_errors.append("Priorisation : ranking_mode invalide ou manquant.")
            if question.get("ranking_mode") == "top_n" and not question.get("top_n"):
                q_errors.append("Priorisation Top N : top_n manquant.")

        elif qtype == "long_answer":
            if not (
                question.get("evaluation_criteria")
                or question.get("rubric")
                or question.get("grading_criteria")
            ):
                q_warnings.append(
                    "Reponse longue : aucun critere d'evaluation. Correction IA/humaine moins fiable."
                )

        audit = classify_question(question)
        if audit.get("detected_type") == "unknown":
            q_warnings.append("L'auditeur ne reconnait pas clairement l'intention.")
        elif (
            audit.get("declared_type")
            and audit.get("detected_type")
            and audit.get("declared_type") != audit.get("detected_type")
        ):
            q_warnings.append(
                "Type declare different du type detecte : "
                f"{audit.get('declared_type')} -> {audit.get('detected_type')}."
            )

        if q_errors:
            errors.extend([f"Q{index}: {msg}" for msg in q_errors])
        if q_warnings:
            warnings.extend([f"Q{index}: {msg}" for msg in q_warnings])

        question_reports.append({
            "index": index,
            "type": qtype,
            "domain": question.get("domain") or "",
            "question": text[:140],
            "errors": q_errors,
            "warnings": q_warnings,
        })

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "questions": question_reports,
        "question_count": len(questions),
        "error_count": len(errors),
        "warning_count": len(warnings),
    }


def template_json_bytes() -> bytes:
    payload = {
        "quiz_title": "Modele import industriel - Quiz Formation",
        "analysis_summary": "Modele JSON V23 enrichi.",
        "questions": [
            {
                "type": "single_choice",
                "training_scope": "CDPO",
                "question_set_type": "Entrainement par domaine",
                "domain": "Principes RGPD",
                "subdomain": "Minimisation",
                "difficulty": "Intermediaire",
                "cognitive_level": "Application",
                "learning_objective": "Choisir une mesure conforme au principe de minimisation.",
                "competency": "Appliquer les principes de protection des donnees.",
                "concept_evaluated": "Minimisation des donnees",
                "context": {
                    "title": "Cas pratique",
                    "text": "Une entreprise souhaite enrichir un formulaire d'inscription avec plusieurs informations facultatives.",
                    "collapsible": True,
                    "expanded": False,
                },
                "media": {
                    "type": "image",
                    "url": "https://exemple.fr/illustration.png",
                    "caption": "Illustration facultative",
                    "alt_text": "Schema du formulaire",
                },
                "question": "Quelle mesure faut-il appliquer en priorite ?",
                "options": [
                    "Collecter toutes les donnees disponibles",
                    "Limiter la collecte aux donnees necessaires",
                    "Conserver les donnees sans limite",
                    "Partager les donnees avec tous les services",
                ],
                "correct_answer": "B",
                "explanation": "Le principe de minimisation limite la collecte aux donnees necessaires.",
                "source_excerpt": "RGPD, article 5(1)(c)",
                "remediation": "Revoir les principes de l'article 5 du RGPD.",
                "quality_score": 100,
            },
            {
                "type": "priority_ranking",
                "training_scope": "CDPO",
                "question_set_type": "Examen blanc",
                "domain": "Violations de donnees",
                "subdomain": "Gestion d'incident",
                "difficulty": "Avance",
                "cognitive_level": "Analyse",
                "question": "Classez les actions de la plus prioritaire a la moins prioritaire.",
                "items": [
                    {"label": "A", "text": "Proteger les personnes et limiter le dommage"},
                    {"label": "B", "text": "Preserver les preuves"},
                    {"label": "C", "text": "Qualifier les donnees et personnes concernees"},
                    {"label": "D", "text": "Mobiliser la gouvernance et le DPO"},
                ],
                "ranking_mode": "rank_all",
                "require_justification": True,
                "evaluation_criteria": [
                    "Coherence de la priorisation",
                    "Justification du raisonnement",
                ],
            },
            {
                "type": "long_answer",
                "training_scope": "CDPO",
                "question_set_type": "Examen blanc",
                "domain": "Fonction DPO",
                "subdomain": "Conseil et controle",
                "difficulty": "Avance",
                "cognitive_level": "Evaluation",
                "question": "Redigez votre analyse et vos recommandations.",
                "max_words": 350,
                "max_points": 10,
                "evaluation_criteria": [
                    "Qualification correcte des enjeux",
                    "Argumentation juridique et operationnelle",
                    "Recommandations proportionnees",
                ],
            },
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def template_csv_bytes() -> bytes:
    headers = [
        "quiz_title",
        "module",
        "training_scope",
        "question_set_type",
        "domain",
        "subdomain",
        "type",
        "difficulty",
        "cognitive_level",
        "learning_objective",
        "competency",
        "concept_evaluated",
        "question",
        "option_a",
        "option_b",
        "option_c",
        "option_d",
        "option_e",
        "option_f",
        "correct_answer",
        "accepted_answers",
        "explanation",
        "feedback_a",
        "feedback_b",
        "feedback_c",
        "feedback_d",
        "feedback_e",
        "feedback_f",
        "remediation",
        "source_excerpt",
        "pairs_json",
        "context_title",
        "context_text",
        "context_collapsible",
        "context_expanded",
        "media_type",
        "media_url",
        "media_caption",
        "media_alt_text",
        "total_points",
        "ranking_mode",
        "top_n",
        "require_justification",
        "correct_order",
        "scale_min",
        "scale_max",
        "max_words",
        "max_points",
        "evaluation_criteria",
        "items_json",
    ]

    sample_rows = [
        {
            "quiz_title": "Modele import industriel - CDPO",
            "module": "RGPD",
            "training_scope": "CDPO",
            "question_set_type": "Entrainement par domaine",
            "domain": "Principes RGPD",
            "subdomain": "Minimisation",
            "type": "single_choice",
            "difficulty": "Intermediaire",
            "cognitive_level": "Application",
            "learning_objective": "Choisir une mesure conforme au principe de minimisation.",
            "competency": "Appliquer les principes de protection des donnees.",
            "concept_evaluated": "Minimisation des donnees",
            "question": "Quelle mesure faut-il appliquer en priorite ?",
            "option_a": "Collecter toutes les donnees disponibles",
            "option_b": "Limiter la collecte aux donnees necessaires",
            "option_c": "Conserver les donnees sans limite",
            "option_d": "Partager les donnees avec tous les services",
            "correct_answer": "B",
            "explanation": "Le principe de minimisation limite la collecte aux donnees necessaires.",
            "remediation": "Revoir les principes de l'article 5 du RGPD.",
            "source_excerpt": "RGPD, article 5(1)(c)",
            "context_title": "Cas pratique",
            "context_text": "Une entreprise souhaite enrichir un formulaire d'inscription avec plusieurs informations facultatives.",
            "context_collapsible": "true",
            "context_expanded": "false",
            "media_type": "image",
            "media_url": "https://exemple.fr/illustration.png",
            "media_caption": "Illustration facultative",
            "media_alt_text": "Schema du formulaire",
        },
        {
            "quiz_title": "Modele import industriel - CDPO",
            "module": "RGPD",
            "training_scope": "CDPO",
            "question_set_type": "Examen blanc",
            "domain": "Violations de donnees",
            "subdomain": "Gestion d'incident",
            "type": "priority_ranking",
            "difficulty": "Avance",
            "cognitive_level": "Analyse",
            "question": "Classez les actions de la plus prioritaire a la moins prioritaire.",
            "ranking_mode": "rank_all",
            "require_justification": "true",
            "evaluation_criteria": "Coherence de la priorisation | Justification du raisonnement",
            "items_json": json.dumps([
                {"label": "A", "text": "Proteger les personnes et limiter le dommage"},
                {"label": "B", "text": "Preserver les preuves"},
                {"label": "C", "text": "Qualifier les donnees et personnes concernees"},
                {"label": "D", "text": "Mobiliser la gouvernance et le DPO"},
            ], ensure_ascii=False),
        },
        {
            "quiz_title": "Modele import industriel - CDPO",
            "module": "RGPD",
            "training_scope": "CDPO",
            "question_set_type": "Examen blanc",
            "domain": "Fonction DPO",
            "subdomain": "Conseil et controle",
            "type": "long_answer",
            "difficulty": "Avance",
            "cognitive_level": "Evaluation",
            "question": "Redigez votre analyse et vos recommandations.",
            "max_words": "350",
            "max_points": "10",
            "evaluation_criteria": (
                "Qualification correcte des enjeux | "
                "Argumentation juridique et operationnelle | "
                "Recommandations proportionnees"
            ),
        },
    ]

    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=headers,
        delimiter=";",
        extrasaction="ignore",
        lineterminator="\n",
    )
    writer.writeheader()
    for row in sample_rows:
        writer.writerow(row)

    return output.getvalue().encode("utf-8-sig")

