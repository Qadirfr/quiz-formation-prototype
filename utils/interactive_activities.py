"""Interactive, keyboard-accessible card activities for Quiz Formation.

Only UI state lives in Streamlit. Answers keep the existing ordering list and
matching dict formats so scoring, snapshots and exports stay compatible.
"""

from __future__ import annotations

import hashlib
import random
from typing import Any


def shuffled_indexes(count: int, seed: str) -> list[int]:
    """Return a stable shuffled card deck, never the source order for 2+ cards."""
    indexes = list(range(count))
    if count > 1:
        digest = hashlib.sha256(seed.encode("utf-8")).digest()
        random.Random(int.from_bytes(digest[:8], "big")).shuffle(indexes)
        if indexes == list(range(count)):
            indexes = indexes[1:] + indexes[:1]
    return indexes


def can_render_ordering(items: list[dict[str, Any]]) -> bool:
    labels = [str(item.get("label") or "").upper() for item in items]
    return len(labels) >= 2 and all(labels) and len(labels) == len(set(labels))


def can_render_matching(pairs: list[dict[str, Any]]) -> bool:
    left = [str(pair.get("left") or "").strip() for pair in pairs]
    right = [str(pair.get("right") or "").strip() for pair in pairs]
    return (
        len(pairs) >= 2
        and all(left)
        and all(right)
        and len({value.casefold() for value in left}) == len(left)
        and len({value.casefold() for value in right}) == len(right)
    )


def clean_sequence(selected: Any, valid_labels: list[str]) -> list[str]:
    valid = set(valid_labels)
    result: list[str] = []
    if not isinstance(selected, list):
        return result
    for raw in selected:
        label = str(raw).upper()
        if label in valid and label not in result:
            result.append(label)
    return result


def move_sequence(selected: list[str], position: int, offset: int) -> list[str]:
    result = list(selected)
    destination = position + offset
    if 0 <= position < len(result) and 0 <= destination < len(result):
        result[position], result[destination] = result[destination], result[position]
    return result


def clean_matches(selected: Any, count: int) -> dict[int, int]:
    if not isinstance(selected, dict):
        return {}
    cleaned: dict[int, int] = {}
    used_right: set[int] = set()
    for raw_left, raw_right in selected.items():
        try:
            left, right = int(raw_left), int(raw_right)
        except (ValueError, TypeError):
            continue
        if 0 <= left < count and 0 <= right < count and left not in cleaned and right not in used_right:
            cleaned[left] = right
            used_right.add(right)
    return cleaned


def matching_answer(pairs: list[dict[str, Any]], matches: Any) -> dict[str, str]:
    valid = clean_matches(matches, len(pairs))
    return {
        str(pairs[left]["left"]): str(pairs[right]["right"])
        for left, right in valid.items()
    }


def render_ordering_cards(items: list[dict[str, Any]], state_key: str) -> list[str]:
    """Build an order by picking cards, then moving/removing them before submission."""
    import streamlit as st

    labels = [str(item["label"]).upper() for item in items]
    descriptions = {str(item["label"]).upper(): str(item.get("text") or "") for item in items}
    selected = clean_sequence(st.session_state.get(state_key), labels)
    st.session_state[state_key] = selected

    st.caption("Défi chronologique : sélectionne les cartes, puis ajuste l'ordre avec les flèches.")
    st.progress(len(selected) / len(labels), text=f"{len(selected)} / {len(labels)} cartes placées")
    if selected:
        st.markdown("**Ton classement**")
        for position, label in enumerate(selected):
            cols = st.columns([8, 1, 1, 1])
            cols[0].write(f"**{position + 1}.** {descriptions[label]}")
            if cols[1].button("↑", key=f"{state_key}_up_{position}", disabled=position == 0, help="Monter"):
                st.session_state[state_key] = move_sequence(selected, position, -1)
                st.rerun()
            if cols[2].button("↓", key=f"{state_key}_down_{position}", disabled=position == len(selected) - 1, help="Descendre"):
                st.session_state[state_key] = move_sequence(selected, position, 1)
                st.rerun()
            if cols[3].button("✕", key=f"{state_key}_remove_{position}", help="Retirer"):
                st.session_state[state_key] = [value for value in selected if value != label]
                st.rerun()

    remaining = [index for index in shuffled_indexes(len(items), state_key) if labels[index] not in selected]
    if remaining:
        st.markdown("**Cartes à placer**")
        cols = st.columns(2)
        for card_index, item_index in enumerate(remaining):
            label = labels[item_index]
            if cols[card_index % 2].button(
                f"＋ {descriptions[label]}", key=f"{state_key}_add_{item_index}", width="stretch"
            ):
                st.session_state[state_key] = selected + [label]
                st.rerun()
    else:
        st.caption("Toutes les cartes sont placées. Tu peux encore changer leur ordre.")

    if selected and st.button("↺ Recommencer le classement", key=f"{state_key}_reset"):
        st.session_state[state_key] = []
        st.rerun()
    return selected


def render_matching_cards(pairs: list[dict[str, Any]], state_key: str) -> dict[str, str]:
    """Associate left/right cards without displaying the answer key before submit."""
    import streamlit as st

    state = st.session_state.get(state_key)
    if not isinstance(state, dict):
        state = {}
    matches = clean_matches(state.get("matches"), len(pairs))
    chosen = state.get("chosen")
    if not isinstance(chosen, int) or chosen not in range(len(pairs)) or chosen in matches:
        chosen = None
    st.session_state[state_key] = {"matches": matches, "chosen": chosen}

    st.caption("Défi associations : choisis une carte de gauche, puis sa correspondance à droite.")
    st.progress(len(matches) / len(pairs), text=f"{len(matches)} / {len(pairs)} associations réalisées")
    left_col, right_col = st.columns(2)
    with left_col:
        st.markdown("**Cartes à associer**")
        for left_index, pair in enumerate(pairs):
            if left_index in matches:
                st.caption(f"✓ {pair['left']} — associé")
                if st.button("↶ Modifier", key=f"{state_key}_undo_{left_index}"):
                    updated = dict(matches)
                    updated.pop(left_index)
                    st.session_state[state_key] = {"matches": updated, "chosen": left_index}
                    st.rerun()
            else:
                if st.button(
                    f"{'● ' if chosen == left_index else '○ '}{pair['left']}",
                    key=f"{state_key}_left_{left_index}",
                    type="primary" if chosen == left_index else "secondary",
                    width="stretch",
                ):
                    st.session_state[state_key] = {"matches": matches, "chosen": left_index}
                    st.rerun()
    with right_col:
        st.markdown("**Réponses proposées**")
        for right_index in shuffled_indexes(len(pairs), state_key):
            if right_index in matches.values():
                continue
            if st.button(
                f"＋ {pairs[right_index]['right']}",
                key=f"{state_key}_right_{right_index}",
                disabled=chosen is None,
                width="stretch",
            ):
                updated = dict(matches)
                updated[chosen] = right_index
                st.session_state[state_key] = {"matches": updated, "chosen": None}
                st.rerun()
    if matches:
        st.markdown("**Tes associations**")
        for left_index in sorted(matches):
            st.write(f"{pairs[left_index]['left']} → {pairs[matches[left_index]]['right']}")
        if st.button("↺ Recommencer les associations", key=f"{state_key}_reset"):
            st.session_state[state_key] = {"matches": {}, "chosen": None}
            st.rerun()
    return matching_answer(pairs, matches)
