from __future__ import annotations

import re
import unicodedata
from collections import Counter
from typing import Any, Dict, Iterable, List


QUESTION_SCHEMA_VERSION = 2

CANONICAL_TYPES = {
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
    "unknown",
}

TYPE_ALIASES = {
    "qcm": "single_choice",
    "choix_unique": "single_choice",
    "single_choice": "single_choice",
    "multiple_choice": "single_choice",
    "vrai_faux": "true_false",
    "true_false": "true_false",
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
    "fill_blank": "fill_blank",
    "fill_in_blank": "fill_blank",
    "fill_in_the_blank": "fill_blank",
    "texte_a_trous": "fill_blank",
    "question_a_trous": "fill_blank",
    "cloze": "fill_blank",
    "completion": "fill_blank",
    "self_assessment": "self_assessment",
    "self_evaluation": "self_assessment",
    "auto_evaluation": "self_assessment",
    "autoevaluation": "self_assessment",
    "self_rating": "self_assessment",
    "likert": "self_assessment",
    "rating_scale": "self_assessment",
    "scale": "self_assessment",
    "point_allocation": "point_allocation",
    "allocation_points": "point_allocation",
    "priority_ranking": "priority_ranking",
    "prioritization": "priority_ranking",
    "priorisation": "priority_ranking",
    "question_courte": "short_answer",
    "short_answer": "short_answer",
    "open_answer": "long_answer",
    "long_answer": "long_answer",
    "essay": "long_answer",
    "essay_response": "long_answer",
}


def normalize_text(value: Any) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_declared_type(value: Any) -> str:
    key = normalize_text(value).replace(" ", "_")
    return TYPE_ALIASES.get(key, key if key in CANONICAL_TYPES else "")


def _has_any(text: str, cues: Iterable[str]) -> bool:
    return any(cue in text for cue in cues)


def _question_text(question: Dict[str, Any]) -> str:
    return str(
        question.get("question")
        or question.get("question_text")
        or question.get("consigne")
        or ""
    ).strip()


def _extract_lettered_items_from_text(text: str) -> List[Dict[str, str]]:
    if not text:
        return []

    marker_patterns = [
        r"chantiers?\s+à\s+prioriser\s*:\s*(.+)",
        r"chantiers?\s+a\s+prioriser\s*:\s*(.+)",
        r"éléments?\s+propos(?:é|e)s?\s*:\s*(.+)",
        r"elements?\s+proposes?\s*:\s*(.+)",
        r"éléments?\s+à\s+remettre\s+dans\s+l[’']?ordre\s*:\s*(.+)",
        r"elements?\s+a\s+remettre\s+dans\s+l[’']?ordre\s*:\s*(.+)",
    ]

    tail = ""
    for pattern in marker_patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            tail = match.group(1).strip()
            break

    if not tail:
        return []

    tail = re.split(
        r"\b(?:justifiez?|expliquez?|argumentez?)\b",
        tail,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0].strip()

    chunks = [chunk.strip() for chunk in tail.split("|") if chunk.strip()]
    items: List[Dict[str, str]] = []
    for idx, chunk in enumerate(chunks):
        match = re.match(r"^\s*([A-Za-z])\s*[\.\)\-:]\s*(.+)$", chunk)
        if match:
            items.append({
                "label": match.group(1).upper(),
                "text": match.group(2).strip(),
            })
        else:
            items.append({
                "label": chr(65 + idx),
                "text": chunk,
            })
    return items


def _extract_total_points(text: str) -> int | None:
    normalized = normalize_text(text)
    patterns = [
        r"(?:total de|disposez de|repartissez)\s+(\d{1,4})\s+points?",
        r"(\d{1,4})\s+points?\s+(?:a|à)\s+repartir",
        r"sur\s+(\d{1,4})\s+points?",
    ]
    for pattern in patterns:
        match = re.search(pattern, normalized)
        if match:
            try:
                return int(match.group(1))
            except Exception:
                return None
    return None


def _looks_true_false(options: Any) -> bool:
    if not isinstance(options, list) or len(options) != 2:
        return False
    normalized = {normalize_text(item) for item in options}
    return normalized in [
        {"vrai", "faux"},
        {"true", "false"},
    ]


def classify_question(question: Dict[str, Any]) -> Dict[str, Any]:
    text = _question_text(question)
    normalized = normalize_text(text)
    raw_type = question.get("type") or question.get("question_type") or ""
    declared = normalize_declared_type(raw_type)
    options = question.get("options") or []
    pairs = question.get("pairs") or []

    detected = declared or "unknown"
    confidence = "medium" if declared else "low"
    reasons: List[str] = []
    issues: List[str] = []

    if re.search(r"\[\s*(?:\.\.\.|…+)\s*\]", text):
        detected = "fill_blank"
        confidence = "high"
        reasons.append("placeholder de texte à trous détecté")

    elif _has_any(normalized, [
        "auto evaluez",
        "auto evaluation",
        "evaluez de 1 a 5 votre maitrise",
        "evaluez votre maitrise de 1 a 5",
        "notez de 1 a 5 votre maitrise",
        "situez votre niveau de 1 a 5",
    ]):
        detected = "self_assessment"
        confidence = "high"
        reasons.append("consigne d'auto-positionnement détectée")

    elif _has_any(normalized, [
        "remettez dans l ordre",
        "remettre dans l ordre",
        "mettre dans l ordre",
        "mettez dans l ordre",
        "classez dans l ordre",
        "classer dans l ordre",
        "ordonner",
        "ordonnez",
        "ordre chronologique",
    ]):
        detected = "ordering"
        confidence = "high"
        reasons.append("consigne d'ordonnancement détectée")

    elif _has_any(normalized, [
        "repartissez vos points",
        "repartir les points",
        "points entre les criteres",
        "points entre ces criteres",
    ]):
        detected = "point_allocation"
        confidence = "high"
        reasons.append("consigne de répartition de points détectée")

    elif _has_any(normalized, [
        "repartissez vos priorites",
        "priorisez ces",
        "prioriser ces",
        "chantiers a prioriser",
        "classez les priorites",
    ]) and _has_any(normalized, ["justifiez", "arbitrage", "prioriser", "priorites"]):
        detected = "priority_ranking"
        confidence = "high"
        reasons.append("consigne de priorisation avec arbitrage détectée")

    elif isinstance(pairs, list) and pairs:
        detected = "matching"
        confidence = "high"
        reasons.append("paires structurées détectées")

    elif _looks_true_false(options):
        detected = "true_false"
        confidence = "high"
        reasons.append("options vrai/faux détectées")

    elif isinstance(options, list) and len(options) >= 2:
        detected = "single_choice"
        confidence = "high"
        reasons.append("plusieurs options structurées détectées")

    elif _has_any(normalized, [
        "redigez",
        "analysez",
        "argumentez",
        "justifiez votre reponse",
        "developpez",
        "proposez une recommandation",
        "expliquez en detail",
    ]):
        detected = "long_answer"
        confidence = "medium"
        reasons.append("consigne de réponse rédigée détectée")

    elif declared:
        reasons.append("type déclaré conservé")

    else:
        detected = "unknown"
        confidence = "low"
        reasons.append("aucun schéma fiable détecté")

    if declared and declared != detected:
        issues.append(f"type_conflict:{declared}->{detected}")

    items = _extract_lettered_items_from_text(text)

    if detected == "point_allocation":
        total_points = question.get("total_points") or _extract_total_points(text)
        if not total_points:
            issues.append("missing_total_points")
        if not (question.get("items") or items):
            issues.append("missing_allocation_items")

    if detected == "priority_ranking":
        if not (question.get("items") or items):
            issues.append("missing_priority_items")
        ranking_mode = question.get("ranking_mode")
        if not ranking_mode:
            issues.append("missing_ranking_mode")

    if detected == "fill_blank":
        blank_count = len(re.findall(r"\[\s*(?:\.\.\.|…+)\s*\]", text))
        if blank_count == 0:
            issues.append("missing_blank_placeholders")
        structured = question.get("blanks") or question.get("correct_answers")
        if blank_count > 1 and not structured:
            correct_answer = str(question.get("correct_answer") or "")
            accepted = question.get("accepted_answers") or []
            if not (
                "|" in correct_answer
                or ";" in correct_answer
                or (isinstance(accepted, list) and len(accepted) == blank_count)
            ):
                issues.append("unstructured_fill_blank_correction")

    if detected == "self_assessment":
        if not (question.get("self_assessment_items") or question.get("items") or options or items):
            issues.append("missing_self_assessment_items")

    if detected == "ordering":
        if not (question.get("ordering_items") or question.get("items") or options or items):
            issues.append("missing_ordering_items")
        if not (
            question.get("correct_order")
            or question.get("expected_order")
            or question.get("correct_answer")
        ):
            issues.append("missing_ordering_correction")

    if detected == "matching" and not pairs:
        issues.append("missing_matching_pairs")

    if detected in {"single_choice", "true_false"}:
        if not options:
            issues.append("missing_options")
        if question.get("correct_answer") in (None, ""):
            issues.append("missing_correct_answer")

    if detected == "long_answer":
        if not (
            question.get("rubric")
            or question.get("evaluation_criteria")
            or question.get("grading_criteria")
        ):
            issues.append("missing_grading_rubric")

    suggested_patch: Dict[str, Any] = {
        "schema_version": QUESTION_SCHEMA_VERSION,
        "type": detected,
    }

    if detected in {"point_allocation", "priority_ranking"} and items:
        suggested_patch["items"] = items

    if detected == "point_allocation":
        total_points = question.get("total_points") or _extract_total_points(text)
        if total_points:
            suggested_patch["total_points"] = int(total_points)

    needs_review = detected == "unknown" or confidence == "low" or bool(issues)

    return {
        "schema_version": QUESTION_SCHEMA_VERSION,
        "declared_type_raw": str(raw_type or ""),
        "declared_type": declared or "",
        "detected_type": detected,
        "confidence": confidence,
        "needs_review": needs_review,
        "issues": issues,
        "reasons": reasons,
        "suggested_patch": suggested_patch,
        "question_preview": text[:240],
    }


def summarize_audit(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    types = Counter(row.get("detected_type") or "unknown" for row in rows)
    confidence = Counter(row.get("confidence") or "unknown" for row in rows)
    issues = Counter(
        issue
        for row in rows
        for issue in (row.get("issues") or [])
    )
    review_count = sum(1 for row in rows if row.get("needs_review"))

    return {
        "total": len(rows),
        "review_count": review_count,
        "clean_count": len(rows) - review_count,
        "by_type": dict(types),
        "by_confidence": dict(confidence),
        "by_issue": dict(issues),
    }
