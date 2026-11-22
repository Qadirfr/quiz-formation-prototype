"""Pure tests for card interactions; no Streamlit or database required."""

from utils.interactive_activities import (
    can_render_matching,
    can_render_ordering,
    clean_matches,
    clean_sequence,
    matching_answer,
    move_sequence,
    shuffled_indexes,
)


def test_shuffle_stable_per_question_and_attempt():
    assert shuffled_indexes(5, "attempt-123-question-2") == shuffled_indexes(5, "attempt-123-question-2")
    assert sorted(shuffled_indexes(5, "attempt-123-question-2")) == list(range(5))


def test_shuffle_does_not_leave_answer_in_source_order():
    assert shuffled_indexes(4, "test") != list(range(4))
    assert shuffled_indexes(2, "test") == [1, 0]


def test_shuffle_handles_empty_and_singleton():
    assert shuffled_indexes(0, "test") == []
    assert shuffled_indexes(1, "test") == [0]


def test_ordering_validates_unique_labels():
    assert can_render_ordering([{"label": "A"}, {"label": "B"}])
    assert not can_render_ordering([{"label": "A"}, {"label": "A"}])
    assert not can_render_ordering([{"label": "A"}])


def test_clean_sequence_ignores_unrecognized_and_duplicates():
    assert clean_sequence(["b", "Z", "B", "A"], ["A", "B", "C"]) == ["B", "A"]
    assert clean_sequence("ABC", ["A", "B", "C"]) == []


def test_move_sequence_swaps_only_valid_positions():
    assert move_sequence(["A", "B", "C"], 2, -1) == ["A", "C", "B"]
    assert move_sequence(["A", "B"], 0, -1) == ["A", "B"]
    assert move_sequence(["A", "B"], 1, 1) == ["A", "B"]


def test_matching_requires_nonempty_and_unique_left():
    assert can_render_matching([{"left": "A", "right": "1"}, {"left": "B", "right": "2"}])
    assert not can_render_matching([{"left": "A", "right": "1"}, {"left": "A", "right": "2"}])
    assert not can_render_matching([{"left": "A", "right": ""}, {"left": "B", "right": "2"}])


def test_matching_rejects_ambiguous_repeated_right_labels():
    assert not can_render_matching([{"left": "A", "right": "1"}, {"left": "B", "right": "1"}])
    assert not can_render_matching([{"left": "A", "right": "One"}, {"left": "B", "right": "one"}])


def test_clean_matches_disallows_reusing_right_card():
    assert clean_matches({0: 1, 1: 1, 2: 0}, 3) == {0: 1, 2: 0}


def test_clean_matches_filters_invalid_positions():
    assert clean_matches({-1: 0, "1": "2", 3: 0, "wrong": 2}, 3) == {1: 2}
    assert clean_matches(None, 3) == {}


def test_matching_answer_keeps_legacy_grading_format():
    pairs = [{"left": "DPO", "right": "Conseil"}, {"left": "Responsable", "right": "Finalités"}]
    assert matching_answer(pairs, {1: 0, 0: 1}) == {"DPO": "Finalités", "Responsable": "Conseil"}
    assert matching_answer(pairs, {0: 0, 1: 1}) == {"DPO": "Conseil", "Responsable": "Finalités"}


def test_matching_answer_partial_omits_unanswered_items():
    pairs = [{"left": "A", "right": "X"}, {"left": "B", "right": "Y"}]
    assert matching_answer(pairs, {1: 0}) == {"B": "X"}


class _RerunRequested(Exception):
    pass


class _FakeStreamlit:
    """Minimal stand-in for Streamlit button-driven reruns."""

    def __init__(self):
        self.session_state = {}
        self.clicked_key = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def columns(self, widths):
        return [self] * (widths if isinstance(widths, int) else len(widths))

    def button(self, label, *, key, disabled=False, **kwargs):
        return self.clicked_key == key and not disabled

    def rerun(self):
        raise _RerunRequested()

    def __getattr__(self, name):
        if name in {"caption", "progress", "markdown", "write"}:
            return lambda *args, **kwargs: None
        raise AttributeError(name)


def test_ordering_cards_buttons_change_sequence(monkeypatch):
    import sys
    import pytest
    from utils.interactive_activities import render_ordering_cards

    fake = _FakeStreamlit()
    monkeypatch.setitem(sys.modules, "streamlit", fake)
    items = [{"label": "A", "text": "Identifier"}, {"label": "B", "text": "Traiter"}]
    assert render_ordering_cards(items, "q1") == []
    fake.clicked_key = "q1_add_1"
    with pytest.raises(_RerunRequested):
        render_ordering_cards(items, "q1")
    assert render_ordering_cards(items, "q1") == ["B"]
    fake.clicked_key = "q1_add_0"
    with pytest.raises(_RerunRequested):
        render_ordering_cards(items, "q1")
    fake.clicked_key = "q1_up_1"
    with pytest.raises(_RerunRequested):
        render_ordering_cards(items, "q1")
    fake.clicked_key = None
    assert render_ordering_cards(items, "q1") == ["A", "B"]
    fake.clicked_key = "q1_remove_0"
    with pytest.raises(_RerunRequested):
        render_ordering_cards(items, "q1")
    fake.clicked_key = None
    assert render_ordering_cards(items, "q1") == ["B"]


def test_matching_cards_buttons_preserve_pairing_format(monkeypatch):
    import sys
    import pytest
    from utils.interactive_activities import render_matching_cards

    fake = _FakeStreamlit()
    monkeypatch.setitem(sys.modules, "streamlit", fake)
    pairs = [{"left": "DPO", "right": "Conseil"}, {"left": "RT", "right": "Finalités"}]
    assert render_matching_cards(pairs, "match") == {}
    fake.clicked_key = "match_left_0"
    with pytest.raises(_RerunRequested):
        render_matching_cards(pairs, "match")
    fake.clicked_key = "match_right_1"
    with pytest.raises(_RerunRequested):
        render_matching_cards(pairs, "match")
    fake.clicked_key = None
    assert render_matching_cards(pairs, "match") == {"DPO": "Finalités"}
    fake.clicked_key = "match_undo_0"
    with pytest.raises(_RerunRequested):
        render_matching_cards(pairs, "match")
    fake.clicked_key = None
    assert render_matching_cards(pairs, "match") == {}
