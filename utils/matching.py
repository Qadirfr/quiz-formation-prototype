"""Validation, ordre d'affichage et notation des exercices d'appariement."""
from __future__ import annotations

import hashlib
import json
import random
import re
import unicodedata
from typing import Any


class MatchingValidationError(ValueError):
    """Une question comporte des associations incomplètes ou ambiguës."""


def _key(value: Any) -> str:
    value = unicodedata.normalize("NFKC", str(value or "")).casefold().strip()
    return re.sub(r"\s+", " ", value)


def validate_matching_pairs(
    raw_pairs: Any, *, min_pairs: int = 2, max_pairs: int = 12
) -> list[dict[str, str]]:
    """Contrôle les paires un-à-un sans modifier celles de la banque."""
    if not isinstance(raw_pairs, list):
        raise MatchingValidationError("Les associations doivent former une liste.")
    if len(raw_pairs) < min_pairs:
        raise MatchingValidationError(f"Prévois au moins {min_pairs} associations complètes.")
    if len(raw_pairs) > max_pairs:
        raise MatchingValidationError(f"Prévois au maximum {max_pairs} associations par exercice.")
    normalized: list[dict[str, str]] = []
    left_seen: set[str] = set()
    right_seen: set[str] = set()
    for number, pair in enumerate(raw_pairs, start=1):
        if not isinstance(pair, dict):
            raise MatchingValidationError(f"Association {number} : paire gauche/droite attendue.")
        left, right = pair.get("left"), pair.get("right")
        if not isinstance(left, str) or not isinstance(right, str):
            raise MatchingValidationError(f"Association {number} : éléments textuels requis.")
        left, right = left.strip(), right.strip()
        if not left or not right:
            raise MatchingValidationError(f"Association {number} : les deux éléments sont obligatoires.")
        if len(left) > 500 or len(right) > 500:
            raise MatchingValidationError(f"Association {number} : 500 caractères maximum par élément.")
        if _key(left) in left_seen:
            raise MatchingValidationError(f"Association {number} : élément gauche répété (« {left} »).")
        if _key(right) in right_seen:
            raise MatchingValidationError(f"Association {number} : réponse droite répétée (« {right} »).")
        left_seen.add(_key(left))
        right_seen.add(_key(right))
        normalized_pair = {"left": left, "right": right}
        if pair.get("explanation"):
            normalized_pair["explanation"] = str(pair["explanation"]).strip()[:2000]
        normalized.append(normalized_pair)
    return normalized


def parse_matching_lines(value: Any) -> list[dict[str, str]]:
    """Analyse strictement les lignes séparées par =>, sans en ignorer."""
    pairs = []
    for number, raw_line in enumerate(str(value or "").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        if "=>" not in line:
            raise MatchingValidationError(f"Ligne {number} : utilise le séparateur « => ».")
        left, right = line.split("=>", 1)
        pairs.append({"left": left.strip(), "right": right.strip()})
    return validate_matching_pairs(pairs)


def ordered_matching_options(question: dict[str, Any], salt: str = "") -> list[str]:
    """Mélange stable par tentative, sans toucher à la correction enregistrée."""
    rights: list[str] = []
    seen: set[str] = set()
    for pair in question.get("pairs") or []:
        if not isinstance(pair, dict) or not isinstance(pair.get("right"), str):
            continue
        right = pair["right"].strip()
        if right and _key(right) not in seen:
            rights.append(right)
            seen.add(_key(right))
    if len(rights) < 2:
        return rights
    fingerprint = json.dumps(
        {"pairs": question.get("pairs"), "salt": str(salt),
         "question": question.get("question", "")},
        ensure_ascii=False, sort_keys=True, default=str,
    )
    seed = int.from_bytes(hashlib.sha256(fingerprint.encode()).digest()[:8], "big")
    shuffled = list(rights)
    random.Random(seed).shuffle(shuffled)
    if shuffled == rights:
        shuffled = shuffled[1:] + shuffled[:1]
    return shuffled


def matching_answer_error(question: dict[str, Any], answer: Any) -> str:
    """Vérifie une réponse sans en divulguer la correction."""
    try:
        pairs = validate_matching_pairs(question.get("pairs") or [], min_pairs=1, max_pairs=50)
    except MatchingValidationError:
        return "Les associations de cet exercice sont incohérentes. Préviens le formateur."
    if not isinstance(answer, dict):
        return "Associe chaque élément avant de valider."
    expected_left = {p["left"] for p in pairs}
    if set(answer) != expected_left:
        return "Associe tous les éléments proposés avant de valider."
    available = {_key(p["right"]) for p in pairs}
    selected: list[str] = []
    for pair in pairs:
        chosen = answer.get(pair["left"])
        if not isinstance(chosen, str) or not chosen.strip():
            return "Associe tous les éléments proposés avant de valider."
        if _key(chosen) not in available:
            return "Une réponse choisie ne fait pas partie des propositions."
        selected.append(_key(chosen))
    if len(set(selected)) != len(selected):
        return "Chaque proposition de droite ne peut être utilisée qu'une seule fois."
    return ""


def evaluate_matching_answer(question: dict[str, Any], answer: Any) -> dict[str, Any]:
    """Attribue une fraction par paire et produit un corrigé explicatif."""
    pairs = question.get("pairs") or []
    expected = {
        p["left"]: p["right"] for p in pairs
        if isinstance(p, dict) and isinstance(p.get("left"), str)
        and isinstance(p.get("right"), str)
    }
    explanation = str(question.get("explanation") or "").strip()
    invalid = matching_answer_error(question, answer)
    if invalid:
        return {
            "score": 0.0, "is_correct": False, "correct_answer": expected,
            "selected_feedback": invalid, "correct_feedback": explanation,
            "invalid_reason": invalid,
        }
    correct_count = 0
    wrong: list[str] = []
    for left, right in expected.items():
        chosen = answer.get(left, "")
        if _key(chosen) == _key(right):
            correct_count += 1
        else:
            wrong.append(f"{left} : choisi « {chosen} », attendu « {right} ».")
    score = correct_count / len(expected) if expected else 0.0
    feedback = (
        f"{correct_count} association(s) correcte(s) sur {len(expected)}. "
        + " ".join(wrong)
        if wrong else f"Toutes les {len(expected)} associations sont correctes."
    )
    items = []
    for pair in pairs:
        line = f"{pair['left']} → {pair['right']}"
        if pair.get("explanation"):
            line += f" : {pair['explanation']}"
        items.append(line)
    correction = "Associations attendues : " + " ; ".join(items) + "."
    if explanation:
        correction += " " + explanation
    return {
        "score": score, "is_correct": score == 1.0, "correct_answer": expected,
        "selected_feedback": feedback, "correct_feedback": correction,
        "invalid_reason": "",
    }
