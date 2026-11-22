"""Tests unitaires sans dépendance de Streamlit pour l'appariement V23.1."""
import pytest

from utils.matching import (
    MatchingValidationError,
    evaluate_matching_answer,
    matching_answer_error,
    ordered_matching_options,
    parse_matching_lines,
    validate_matching_pairs,
)


@pytest.fixture
def question():
    return {
        "type": "matching",
        "question": "Associe chaque acteur à son rôle.",
        "pairs": [
            {"left": "Responsable", "right": "Détermine les finalités",
             "explanation": "Il décide des objectifs du traitement."},
            {"left": "Sous-traitant", "right": "Agit pour un responsable"},
            {"left": "DPO", "right": "Conseille et contrôle"},
        ],
        "explanation": "Vérifier les rôles du RGPD.",
    }


def test_normalization_preserves_order_and_explanations(question):
    assert validate_matching_pairs(question["pairs"]) == question["pairs"]


@pytest.mark.parametrize("pairs", [
    [],
    [{"left": "Un", "right": "1"}],
    [{"left": "Un", "right": "1"}, {"left": "", "right": "2"}],
    [{"left": "Un", "right": "1"}, {"left": "un ", "right": "2"}],
    [{"left": "Un", "right": "1"}, {"left": "Deux", "right": " 1 "}],
    [{"left": "Un", "right": "1"}, {"left": "Deux"}],
    [{"left": "Un", "right": "1"}, "Deux => 2"],
    [{"left": "Un", "right": "1"}, {"left": "Deux", "right": None}],
])
def test_reject_bad_or_ambiguous_pairs(pairs):
    with pytest.raises(MatchingValidationError):
        validate_matching_pairs(pairs)


def test_rejects_more_than_twelve_pairs():
    with pytest.raises(MatchingValidationError):
        validate_matching_pairs(
            [{"left": f"L{i}", "right": f"R{i}"} for i in range(13)]
        )


def test_manual_parser_validates_every_line():
    assert parse_matching_lines("A => 1\nB => 2") == [
        {"left": "A", "right": "1"}, {"left": "B", "right": "2"},
    ]
    with pytest.raises(MatchingValidationError, match="Ligne 2"):
        parse_matching_lines("A => 1\nincorrect\nB => 2")


def test_stable_options_do_not_mutate_source(question):
    source = [p["right"] for p in question["pairs"]]
    a = ordered_matching_options(question, salt="attempt-42")
    b = ordered_matching_options(question, salt="attempt-42")
    assert a == b
    assert a != source
    assert set(a) == set(source)
    assert [p["right"] for p in question["pairs"]] == source


def test_complete_correct_answer(question):
    answer = {p["left"]: p["right"] for p in question["pairs"]}
    result = evaluate_matching_answer(question, answer)
    assert result["is_correct"] is True
    assert result["score"] == 1.0
    assert "Vérifier les rôles du RGPD." in result["correct_feedback"]
    assert "Il décide des objectifs" in result["correct_feedback"]


def test_partial_credit_and_feedback(question):
    answer = {
        "Responsable": "Détermine les finalités",
        "Sous-traitant": "Conseille et contrôle",
        "DPO": "Agit pour un responsable",
    }
    result = evaluate_matching_answer(question, answer)
    assert result["is_correct"] is False
    assert result["score"] == pytest.approx(1 / 3)
    assert "1 association(s) correcte(s) sur 3" in result["selected_feedback"]
    assert result["invalid_reason"] == ""


@pytest.mark.parametrize("answer", [
    {},
    {"Responsable": "Détermine les finalités"},
    {"Responsable": "", "Sous-traitant": "Agit pour un responsable",
     "DPO": "Conseille et contrôle"},
    {"Responsable": "Détermine les finalités",
     "Sous-traitant": "Détermine les finalités",
     "DPO": "Conseille et contrôle"},
    {"Responsable": "Valeur non proposée",
     "Sous-traitant": "Agit pour un responsable",
     "DPO": "Conseille et contrôle"},
])
def test_invalid_attempts_do_not_receive_credit(question, answer):
    assert matching_answer_error(question, answer)
    result = evaluate_matching_answer(question, answer)
    assert result["score"] == 0
    assert result["invalid_reason"]


def test_one_pair_legacy_question_is_graduable():
    q = {"type": "matching", "pairs": [{"left": "A", "right": "B"}]}
    assert evaluate_matching_answer(q, {"A": "B"})["score"] == 1.0
    with pytest.raises(MatchingValidationError):
        validate_matching_pairs(q["pairs"])


def test_invalid_legacy_duplicate_right_is_refused():
    q = {
        "type": "matching",
        "pairs": [
            {"left": "A", "right": "1"},
            {"left": "B", "right": "1"},
        ],
    }
    result = evaluate_matching_answer(q, {"A": "1", "B": "1"})
    assert result["invalid_reason"]
    assert result["score"] == 0


def test_unicode_and_whitespace_normalization(question):
    answer = {
        "Responsable": " détermine  les finalités ",
        "Sous-traitant": "AGIT POUR UN RESPONSABLE",
        "DPO": "Conseille et contrôle",
    }
    assert evaluate_matching_answer(question, answer)["score"] == 1.0
