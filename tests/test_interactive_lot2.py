"""Lot 2: word bank, ranked Top N and live allocation without a database."""
import sys

import pytest

from utils.interactive_lot2 import (
    can_render_word_bank,
    clean_word_slots,
    is_complete_decision,
    normalize_word,
    parse_word_bank,
    ranking_target,
    render_point_budget,
    render_priority_cards,
    render_word_bank_tokens,
    usable_word_bank,
)


def test_word_bank_reads_excel_cell_json_and_list():
    assert parse_word_bank("DPO | responsable | intrus") == ["DPO", "responsable", "intrus"]
    assert parse_word_bank('["DPO", "audit"]') == ["DPO", "audit"]
    assert parse_word_bank(["A", " A ", "", "B"]) == ["A", "A", "B"]


def test_word_bank_accepts_accents_and_repeated_correct_words():
    assert normalize_word(" Sécurité ") == "securite"
    assert usable_word_bank(["Contrôle", "Risque", "Contrôle"], ["controle", "contrôle"])
    assert not usable_word_bank(["Contrôle", "Risque"], ["contrôle", "controle"])
    assert not usable_word_bank(["Audit"], ["SÉCURITÉ"])


def test_word_bank_validates_legacy_and_new_questions():
    q = {
        "type": "fill_blank", "question": "Le [...] vérifie le [...]",
        "correct_answers": ["DPO", "risque"],
        "word_bank": ["risque", "DPO", "audit"],
    }
    assert can_render_word_bank(q, 2)
    assert not can_render_word_bank(q, 3)
    q["word_bank"] = ["DPO", "audit"]
    assert not can_render_word_bank(q, 2)


def test_clean_word_slots_filters_duplicate_token_and_invalid_position():
    assert clean_word_slots({1: 0, 2: 0, 3: 2, "a": 1}, 3, 3) == {1: 0, 3: 2}


def test_ranking_target_and_completion():
    q = {
        "type": "priority_ranking", "ranking_mode": "top_n", "top_n": 2,
        "items": [{"label": "A"}, {"label": "B"}, {"label": "C"}],
        "require_justification": True,
    }
    assert ranking_target(q, 3) == 2
    assert ranking_target({**q, "top_n": 10}, 3) == 3
    assert not is_complete_decision(q, {"ranking": ["A"], "justification": "motif"})
    assert not is_complete_decision(q, {"ranking": ["A", "B"], "justification": ""})
    assert is_complete_decision(q, {"ranking": ["B", "C"], "justification": "exposition"})
    assert not is_complete_decision(q, {"ranking": ["B", "B"], "justification": "exposition"})


def test_point_budget_completion_checks_total_and_justification():
    q = {
        "type": "point_allocation", "total_points": 100,
        "items": [{"label": "A"}, {"label": "B"}],
        "require_justification": True,
    }
    assert not is_complete_decision(q, {"allocations": {"A": 40, "B": 40}, "justification": "motif"})
    assert not is_complete_decision(q, {"allocations": {"A": 70, "B": 40}, "justification": "motif"})
    assert not is_complete_decision(q, {"allocations": {"A": 60, "B": 40}, "justification": ""})
    assert is_complete_decision(q, {"allocations": {"A": 60, "B": 40}, "justification": "motif"})


def test_word_bank_completion_is_not_blocked_by_justification():
    q = {"type": "fill_blank", "question": "Le [...] analyse le [...]", "word_bank": ["DPO", "risque"]}
    assert is_complete_decision(q, {"1": "DPO", "2": "risque"})
    assert not is_complete_decision(q, {"1": "DPO"})


class Rerun(Exception):
    pass


class FakeStreamlit:
    def __init__(self):
        self.session_state = {}
        self.clicked_key = ""
        self.justification = "Choix justifié"
        self.slider_values = {}
        self.messages = []

    def columns(self, widths):
        return [self] * (widths if isinstance(widths, int) else len(widths))

    def button(self, label, *, key, disabled=False, **kwargs):
        return key == self.clicked_key and not disabled

    def rerun(self):
        raise Rerun()

    def slider(self, label, *, key, **kwargs):
        return self.slider_values.get(key, 0)

    def text_area(self, label, *, key, **kwargs):
        return self.justification

    def __getattr__(self, name):
        if name in {"caption", "progress", "markdown", "write", "info", "error", "success"}:
            return lambda *args, **kwargs: self.messages.append((name, args))
        raise AttributeError(name)


def test_word_bank_buttons_place_and_replace_tokens(monkeypatch):
    fake = FakeStreamlit()
    monkeypatch.setitem(sys.modules, "streamlit", fake)
    words = ["DPO", "sous-traitant", "responsable"]
    assert render_word_bank_tokens(words, 2, "word") == {}
    fake.clicked_key = "word_word_0"
    with pytest.raises(Rerun):
        render_word_bank_tokens(words, 2, "word")
    fake.clicked_key = ""
    assert render_word_bank_tokens(words, 2, "word") == {"1": "DPO"}
    fake.clicked_key = "word_word_2"
    with pytest.raises(Rerun):
        render_word_bank_tokens(words, 2, "word")
    fake.clicked_key = ""
    assert render_word_bank_tokens(words, 2, "word") == {"1": "DPO", "2": "responsable"}
    fake.clicked_key = "word_slot_1"
    with pytest.raises(Rerun):
        render_word_bank_tokens(words, 2, "word")
    fake.clicked_key = "word_word_1"
    with pytest.raises(Rerun):
        render_word_bank_tokens(words, 2, "word")
    fake.clicked_key = ""
    assert render_word_bank_tokens(words, 2, "word") == {
        "1": "sous-traitant", "2": "responsable"
    }


def test_priority_cards_use_existing_ordering_renderer(monkeypatch):
    fake = FakeStreamlit()
    monkeypatch.setitem(sys.modules, "streamlit", fake)
    items = [{"label": "A", "text": "Audit"}, {"label": "B", "text": "SSI"}, {"label": "C", "text": "RGPD"}]
    q = {"type": "priority_ranking", "ranking_mode": "top_n", "top_n": 2}
    assert render_priority_cards(q, items, "prio") == {"ranking": [], "justification": "Choix justifié"}
    fake.clicked_key = "prio_cards_add_1"
    with pytest.raises(Rerun):
        render_priority_cards(q, items, "prio")
    fake.clicked_key = "prio_cards_add_2"
    with pytest.raises(Rerun):
        render_priority_cards(q, items, "prio")
    fake.clicked_key = ""
    assert render_priority_cards(q, items, "prio")["ranking"] == ["B", "C"]
    assert len(fake.session_state["prio_cards"]) == 2


def test_point_budget_shows_live_balance_and_unchanged_answer_format(monkeypatch):
    fake = FakeStreamlit()
    fake.slider_values = {"budget_slider_A": 65, "budget_slider_B": 35}
    monkeypatch.setitem(sys.modules, "streamlit", fake)
    q = {"type": "point_allocation", "total_points": 100, "require_justification": True}
    items = [{"label": "A", "text": "IAM"}, {"label": "B", "text": "PCA"}]
    result = render_point_budget(q, items, "budget")
    assert result == {
        "allocations": {"A": 65, "B": 35}, "total": 100, "justification": "Choix justifié"
    }
    assert is_complete_decision({**q, "items": items}, result)
    assert any(m[0] == "success" for m in fake.messages)
    fake.slider_values["budget_slider_B"] = 45
    over = render_point_budget(q, items, "budget")
    assert over["total"] == 110
    assert any(m[0] == "error" for m in fake.messages)
