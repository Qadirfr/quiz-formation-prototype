"""Lot 2 — lightweight, interactive activities backed by existing answer formats.

No database operations. Interactive controls use Streamlit's built-in widgets.
Ranking returns {"ranking": [...], "justification": "..."}.
Word bank returns {"1": "word", ...}.
Point allocation returns {"allocations": {...}, "justification": "...", "total": 0}.
"""
from __future__ import annotations

from collections import Counter
import re
import unicodedata
from typing import Any

from utils.interactive_activities import clean_sequence, render_ordering_cards, shuffled_indexes


def normalize_word(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").strip())
    return " ".join("".join(c for c in text if not unicodedata.combining(c)).casefold().split())


def parse_word_bank(value: Any) -> list[str]:
    """Read a JSON list, a Python list, or Excel-friendly 'mot | autre mot'."""
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    text = str(value or "").strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            import json
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return parse_word_bank(parsed)
        except (ValueError, TypeError):
            pass
    return [x.strip() for x in re.split(r"[\n|;]+", text) if x.strip()]


def usable_word_bank(words: Any, expected: Any) -> bool:
    """Every expected word must be present as a reusable-once token."""
    options = parse_word_bank(words)
    answers = parse_word_bank(expected)
    if not answers or len(options) < len(answers):
        return False
    word_counts = Counter(normalize_word(x) for x in options)
    expected_counts = Counter(normalize_word(x) for x in answers)
    return all(word_counts[token] >= count for token, count in expected_counts.items())


def can_render_word_bank(question: dict[str, Any], blanks: int) -> bool:
    if blanks <= 0:
        return False
    words = parse_word_bank(question.get("word_bank"))
    expected = parse_word_bank(question.get("correct_answers"))
    if len(expected) != blanks:
        correct_answer = str(question.get("correct_answer") or "").strip()
        expected = parse_word_bank(correct_answer)
    return len(expected) == blanks and usable_word_bank(words, expected)


def clean_word_slots(raw: Any, option_count: int, blanks: int) -> dict[int, int]:
    if not isinstance(raw, dict):
        return {}
    out: dict[int, int] = {}
    used: set[int] = set()
    for raw_slot, raw_token in raw.items():
        try:
            slot, token = int(raw_slot), int(raw_token)
        except (ValueError, TypeError):
            continue
        if 1 <= slot <= blanks and 0 <= token < option_count and token not in used:
            out[slot] = token
            used.add(token)
    return out


def render_word_bank_tokens(
    words: list[str], blank_count: int, state_key: str
) -> dict[str, str]:
    """Pick a blank, then a token; tokens cannot be used twice by index."""
    import streamlit as st

    state = st.session_state.get(state_key)
    if not isinstance(state, dict):
        state = {}
    placed = clean_word_slots(state.get("placed"), len(words), blank_count)
    active = state.get("active")
    if not isinstance(active, int) or not 1 <= active <= blank_count:
        active = next((i for i in range(1, blank_count + 1) if i not in placed), 1)
    st.session_state[state_key] = {"placed": placed, "active": active}

    st.caption("Choisis un trou, puis une étiquette. Tu peux remplacer une étiquette avant de valider.")
    st.progress(len(placed) / blank_count, text=f"{len(placed)} / {blank_count} trous complétés")
    st.markdown("**Choisir le trou à compléter**")
    cols = st.columns(min(blank_count, 4))
    for index in range(1, blank_count + 1):
        text = words[placed[index]] if index in placed else "______"
        if cols[(index - 1) % len(cols)].button(
            f"[{index}] {text}",
            key=f"{state_key}_slot_{index}",
            type="primary" if active == index else "secondary",
            width="stretch",
        ):
            st.session_state[state_key] = {"placed": placed, "active": index}
            st.rerun()

    remaining = [
        index for index in shuffled_indexes(len(words), state_key)
        if index not in placed.values()
    ]
    if remaining:
        st.markdown("**Étiquettes proposées**")
        cols = st.columns(2)
        for position, token_index in enumerate(remaining):
            if cols[position % 2].button(
                f"＋ {words[token_index]}",
                key=f"{state_key}_word_{token_index}",
                width="stretch",
            ):
                next_placed = dict(placed)
                next_placed[active] = token_index
                next_active = next(
                    (i for i in range(active + 1, blank_count + 1) if i not in next_placed),
                    next((i for i in range(1, blank_count + 1) if i not in next_placed), active),
                )
                st.session_state[state_key] = {"placed": next_placed, "active": next_active}
                st.rerun()
    else:
        st.caption("Toutes les étiquettes nécessaires sont placées.")

    if placed and st.button("↺ Effacer toutes mes réponses", key=f"{state_key}_reset"):
        st.session_state[state_key] = {"placed": {}, "active": 1}
        st.rerun()

    return {str(slot): words[index] for slot, index in sorted(placed.items())}


def ranking_target(question: dict[str, Any], count: int) -> int:
    if str(question.get("ranking_mode") or "rank_all") == "top_n":
        try:
            wanted = int(question.get("top_n") or count)
        except (ValueError, TypeError):
            wanted = count
        return max(1, min(wanted, count))
    return count


def render_priority_cards(
    question: dict[str, Any], items: list[dict[str, Any]], state_key: str
) -> dict[str, Any]:
    import streamlit as st

    target = ranking_target(question, len(items))
    st.caption(
        f"Choisis les {target} priorités et classe-les de la plus urgente à la moins urgente."
        if target < len(items)
        else "Classe les actions de la plus prioritaire à la moins prioritaire."
    )
    ranking = render_ordering_cards(
        items, f"{state_key}_cards", max_cards=target,
        caption="Sélectionne les cartes, puis corrige leur ordre avec ↑ et ↓.",
    )
    justification = ""
    if question.get("require_justification", True):
        justification = st.text_area(
            "Justifie ton arbitrage",
            key=f"{state_key}_justification",
            height=120,
        )
    return {"ranking": ranking, "justification": justification}


def render_point_budget(
    question: dict[str, Any], items: list[dict[str, Any]], state_key: str
) -> dict[str, Any]:
    """Live budget indicator and sliders; existing manual grading is unchanged."""
    import streamlit as st

    total_points = int(question.get("total_points") or 0)
    allocations: dict[str, int] = {}
    st.caption(f"Répartis exactement {total_points} points. Le solde évolue à chaque choix.")
    for item in items:
        label = str(item.get("label") or "").upper()
        value = st.slider(
            f"{label}. {item.get('text', '')}",
            min_value=0,
            max_value=total_points,
            step=1,
            value=0,
            key=f"{state_key}_slider_{label}",
        )
        allocations[label] = int(value)
    used = sum(allocations.values())
    st.progress(
        min(1.0, used / total_points),
        text=f"Budget attribué : {used} / {total_points} points",
    )
    if used > total_points:
        st.error(f"Tu as dépassé le budget de {used - total_points} point(s). Réduis une ou plusieurs lignes.")
    elif used < total_points:
        st.info(f"Il reste {total_points - used} point(s) à répartir.")
    else:
        st.success("Budget entièrement réparti. Tu peux valider ton arbitrage.")
    justification = ""
    if question.get("require_justification", True):
        justification = st.text_area(
            "Justifie ton arbitrage",
            height=120,
            key=f"{state_key}_justification",
        )
    return {
        "allocations": allocations,
        "total": used,
        "justification": justification,
    }


def is_complete_decision(question: dict[str, Any], answer: Any) -> bool:
    """Protect live controls from premature submissions."""
    qtype = str(question.get("type") or "")
    if qtype == "branching_scenario":
        from utils.interactive_scenarios import is_scenario_complete
        return is_scenario_complete(question, answer)
    if qtype == "image_hotspots":
        from utils.visual_hotspots import visual_complete
        return visual_complete(question, answer)
    if qtype == "priority_ranking":
        if not isinstance(answer, dict):
            return False
        items = question.get("items") or []
        ranking = clean_sequence(answer.get("ranking"), [
            str(item.get("label") or "").upper() for item in items
        ])
        completed = len(ranking) == ranking_target(question, len(items))
    elif qtype == "point_allocation":
        if not isinstance(answer, dict):
            return False
        try:
            total = int(question.get("total_points") or 0)
            given = answer.get("allocations") or {}
            completed = total > 0 and sum(int(x) for x in given.values()) == total
        except (TypeError, ValueError):
            return False
    elif qtype == "fill_blank" and question.get("word_bank"):
        if not isinstance(answer, dict):
            return False
        blanks = len(re.findall(r"\[\s*(?:\.\.\.|…+)\s*\]", question.get("question") or ""))
        return blanks > 0 and len(answer) == blanks and all(
            str(value).strip() for value in answer.values()
        )
    else:
        return True
    return completed and (
        not question.get("require_justification", True)
        or bool(str(answer.get("justification") or "").strip())
    )
