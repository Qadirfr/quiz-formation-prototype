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
    writer = csv.writer(output, delimiter=";")
    writer.writerow([
        "numero",
        "type",
        "niveau",
        "niveau_cognitif",
        "competence_evaluee",
        "notion_evaluee",
        "score_qualite",
        "notes_qualite",
        "question",
        "option_a",
        "option_b",
        "option_c",
        "option_d",
        "paires_json",
        "reponse_correcte",
        "explication",
        "extrait_source",
        "context_title",
        "context_text",
        "context_collapsible",
        "media_type",
        "media_url",
        "media_caption",
        "media_alt_text",
        "total_points",
        "ranking_mode",
        "require_justification",
        "max_words",
        "evaluation_criteria",
    ])

    for i, question in enumerate(quiz.get("questions", []), start=1):
        options: List[Any] = question.get("options") or []
        text_options = [_option_to_text(o) for o in options]
        padded_options = (text_options + ["", "", "", ""])[:4]
        pairs = question.get("pairs") or []
        pairs_json = json.dumps(pairs, ensure_ascii=False)

        writer.writerow([
            i,
            question.get("type", ""),
            question.get("difficulty", ""),
            question.get("cognitive_level", ""),
            question.get("competency", ""),
            question.get("concept_evaluated", ""),
            question.get("quality_score", ""),
            question.get("quality_notes", ""),
            question.get("question", ""),
            *padded_options,
            pairs_json,
            question.get("correct_answer", ""),
            question.get("explanation", ""),
            question.get("source_excerpt", ""),
            (
                (question.get("context") or {}).get("title", "")
                if isinstance(question.get("context"), dict)
                else ""
            ),
            (
                (question.get("context") or {}).get("text", "")
                if isinstance(question.get("context"), dict)
                else str(question.get("context") or "")
            ),
            (
                (question.get("context") or {}).get("collapsible", "")
                if isinstance(question.get("context"), dict)
                else ""
            ),
            (
                (question.get("media") or {}).get("type", "")
                if isinstance(question.get("media"), dict)
                else ""
            ),
            (
                (question.get("media") or {}).get("url", "")
                if isinstance(question.get("media"), dict)
                else question.get("image_url", "")
            ),
            (
                (question.get("media") or {}).get("caption", "")
                if isinstance(question.get("media"), dict)
                else ""
            ),
            (
                (question.get("media") or {}).get("alt_text", "")
                if isinstance(question.get("media"), dict)
                else ""
            ),
            question.get("total_points", ""),
            question.get("ranking_mode", ""),
            question.get("require_justification", ""),
            question.get("max_words", ""),
            " | ".join(
                str(item)
                for item in (question.get("evaluation_criteria") or [])
            )
            if isinstance(question.get("evaluation_criteria"), list)
            else str(question.get("evaluation_criteria") or ""),
        ])

    return output.getvalue().encode("utf-8-sig")
