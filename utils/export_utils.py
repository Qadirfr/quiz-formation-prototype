from __future__ import annotations

import csv
import io
import json
from typing import Any, Dict, List


def quiz_to_json_bytes(quiz: Dict[str, Any]) -> bytes:
    return json.dumps(quiz, ensure_ascii=False, indent=2).encode("utf-8")


def _option_to_text(option: Any) -> str:
    if isinstance(option, (dict, list)):
        return json.dumps(option, ensure_ascii=False)
    return str(option)


def quiz_to_markdown(quiz: Dict[str, Any]) -> str:
    title = quiz.get("quiz_title", "Quiz")
    lines = [f"# {title}", ""]

    analysis = quiz.get("analysis") or {}
    if analysis:
        lines.append("## Analyse pedagogique")
        lines.append("")
        lines.append(f"**Objectif :** {analysis.get('training_goal', '')}")
        lines.append("")
        concepts = analysis.get("key_concepts") or []
        if concepts:
            lines.append("### Notions cles")
            for concept in concepts:
                lines.append(f"- **{concept.get('concept', '')}** : {concept.get('definition', '')}")
            lines.append("")

    quality = quiz.get("quality_summary") or {}
    if quality:
        lines.append("## Synthese qualite")
        lines.append("")
        lines.append(f"- Score moyen : {quality.get('average_score', 0)}")
        lines.append(f"- Questions sous 70 : {quality.get('low_quality_count', 0)}")
        lines.append(f"- Commentaire : {quality.get('warning', '')}")
        lines.append("")

    for i, question in enumerate(quiz.get("questions", []), start=1):
        qtype = question.get("type", "")
        lines.append(f"## Question {i}")
        lines.append(f"**Type :** {qtype}")
        lines.append(f"**Niveau :** {question.get('difficulty', '')}")
        lines.append(f"**Niveau cognitif :** {question.get('cognitive_level', '')}")
        lines.append(f"**Competence evaluee :** {question.get('competency', '')}")
        lines.append(f"**Notion evaluee :** {question.get('concept_evaluated', '')}")
        lines.append(f"**Score qualite :** {question.get('quality_score', '')}")
        lines.append("")
        context = (
            question.get("context")
            or question.get("case_context")
            or question.get("case_study")
        )
        if context:
            if isinstance(context, str):
                lines.append("### Cas pratique / contexte")
                lines.append(context)
            elif isinstance(context, dict):
                lines.append(
                    f"### {context.get('title') or 'Cas pratique / contexte'}"
                )
                lines.append(
                    str(
                        context.get("text")
                        or context.get("content")
                        or context.get("description")
                        or ""
                    )
                )
            lines.append("")

        media = question.get("media")
        if isinstance(media, dict):
            media_url = media.get("url") or media.get("path") or media.get("source")
            if media_url:
                lines.append(f"**Média :** {media_url}")
                if media.get("caption"):
                    lines.append(f"**Légende :** {media.get('caption')}")
                lines.append("")
        elif question.get("image_url"):
            lines.append(f"**Image :** {question.get('image_url')}")
            lines.append("")

        lines.append(question.get("question", ""))
        lines.append("")

        pairs = question.get("pairs") or []
        options = question.get("options") or []

        if qtype == "matching" and pairs:
            lines.append("### Colonne A")
            for idx, pair in enumerate(pairs, start=1):
                lines.append(f"{idx}. {pair.get('left', '')}")
            lines.append("")
            lines.append("### Colonne B")
            for idx, pair in enumerate(pairs, start=1):
                label = chr(64 + idx)
                lines.append(f"{label}. {pair.get('right', '')}")
            lines.append("")
            lines.append("### Correction")
            for pair in pairs:
                lines.append(f"- {pair.get('left', '')} -> {pair.get('right', '')}")
        else:
            for idx, option in enumerate(options):
                label = chr(65 + idx)
                lines.append(f"- {label}. {_option_to_text(option)}")

        lines.append("")
        lines.append(f"**Reponse correcte :** {question.get('correct_answer', '')}")
        lines.append(f"**Explication :** {question.get('explanation', '')}")
        lines.append(f"**Notes qualite :** {question.get('quality_notes', '')}")
        if question.get("source_excerpt"):
            lines.append(f"**Extrait source :** {question.get('source_excerpt')}")
        lines.append("")

    return "\n".join(lines)


def quiz_to_markdown_bytes(quiz: Dict[str, Any]) -> bytes:
    return quiz_to_markdown(quiz).encode("utf-8")


def quiz_to_csv_bytes(quiz: Dict[str, Any]) -> bytes:
    output = io.StringIO()
    fieldnames = [
        "numero",
        "quiz_title",
        "training_scope",
        "question_set_type",
        "case_id",
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
        "remediation",
        "source_excerpt",
        "pairs_json",
        "items_json",
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
        "quality_score",
        "quality_notes",
    ]
    writer = csv.DictWriter(
        output,
        fieldnames=fieldnames,
        delimiter=";",
        extrasaction="ignore",
        lineterminator="\n",
    )
    writer.writeheader()

    title = quiz.get("quiz_title", "Quiz")
    for i, question in enumerate(quiz.get("questions", []), start=1):
        options: List[Any] = question.get("options") or []
        text_options = [_option_to_text(o) for o in options]
        padded_options = (text_options + [""] * 6)[:6]

        context = question.get("context")
        if isinstance(context, dict):
            context_title = context.get("title", "")
            context_text = (
                context.get("text")
                or context.get("content")
                or context.get("description")
                or ""
            )
            context_collapsible = context.get("collapsible", "")
            context_expanded = context.get("expanded", "")
        else:
            context_title = ""
            context_text = str(context or "")
            context_collapsible = ""
            context_expanded = ""

        media = question.get("media")
        if isinstance(media, dict):
            media_type = media.get("type", "")
            media_url = media.get("url") or media.get("path") or media.get("source") or ""
            media_caption = media.get("caption", "")
            media_alt = media.get("alt_text") or media.get("alt") or ""
        else:
            media_type = ""
            media_url = question.get("image_url", "")
            media_caption = question.get("image_caption", "")
            media_alt = question.get("image_alt_text", "")

        accepted = question.get("accepted_answers") or []
        if isinstance(accepted, list):
            accepted_text = " | ".join(str(item) for item in accepted)
        else:
            accepted_text = str(accepted or "")

        criteria = question.get("evaluation_criteria") or []
        if isinstance(criteria, list):
            criteria_text = " | ".join(str(item) for item in criteria)
        else:
            criteria_text = str(criteria or "")

        correct_order = question.get("correct_order") or question.get("expected_order") or ""
        if isinstance(correct_order, list):
            correct_order = "".join(str(item) for item in correct_order)

        writer.writerow({
            "numero": i,
            "quiz_title": title,
            "training_scope": question.get("training_scope", ""),
            "question_set_type": question.get("question_set_type", ""),
            "case_id": question.get("case_id", ""),
            "domain": question.get("domain", ""),
            "subdomain": question.get("subdomain", ""),
            "type": question.get("type", ""),
            "difficulty": question.get("difficulty", ""),
            "cognitive_level": question.get("cognitive_level", ""),
            "learning_objective": question.get("learning_objective", ""),
            "competency": question.get("competency", ""),
            "concept_evaluated": question.get("concept_evaluated", ""),
            "question": question.get("question", ""),
            "option_a": padded_options[0],
            "option_b": padded_options[1],
            "option_c": padded_options[2],
            "option_d": padded_options[3],
            "option_e": padded_options[4],
            "option_f": padded_options[5],
            "correct_answer": question.get("correct_answer", ""),
            "accepted_answers": accepted_text,
            "explanation": question.get("explanation", ""),
            "remediation": question.get("remediation", ""),
            "source_excerpt": question.get("source_excerpt", ""),
            "pairs_json": json.dumps(question.get("pairs") or [], ensure_ascii=False),
            "items_json": json.dumps(question.get("items") or [], ensure_ascii=False),
            "context_title": context_title,
            "context_text": context_text,
            "context_collapsible": context_collapsible,
            "context_expanded": context_expanded,
            "media_type": media_type,
            "media_url": media_url,
            "media_caption": media_caption,
            "media_alt_text": media_alt,
            "total_points": question.get("total_points", ""),
            "ranking_mode": question.get("ranking_mode", ""),
            "top_n": question.get("top_n", ""),
            "require_justification": question.get("require_justification", ""),
            "correct_order": correct_order,
            "scale_min": question.get("scale_min", ""),
            "scale_max": question.get("scale_max", ""),
            "max_words": question.get("max_words", ""),
            "max_points": question.get("max_points", ""),
            "evaluation_criteria": criteria_text,
            "quality_score": question.get("quality_score", ""),
            "quality_notes": question.get("quality_notes", ""),
        })

    return output.getvalue().encode("utf-8-sig")

