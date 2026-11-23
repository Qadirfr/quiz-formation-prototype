"""The existing SQLite bank accepts all five interactive formats unchanged."""

import io

from utils.interactive_templates import interactive_xlsx_bytes
from utils.table_import import read_quiz_table, validate_imported_quiz


class _Upload(io.BytesIO):
    def __init__(self, payload):
        super().__init__(payload)
        self.name = "lot2_ateliers.xlsx"


def test_full_interactive_lot_imported_to_existing_question_bank(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_DATABASE_MODE", "sqlite")
    monkeypatch.setenv("SQLITE_DB_PATH", str(tmp_path / "quiz-lot2.db"))

    from utils.question_bank import (
        add_quiz_to_bank, get_question_bank_stats, select_random_questions_scoped
    )

    quiz = read_quiz_table(_Upload(interactive_xlsx_bytes()))
    assert validate_imported_quiz(quiz)["valid"]
    result = add_quiz_to_bank(quiz)
    assert result["added"] == 9, result
    assert result["ignored"] == 0

    stats = get_question_bank_stats()
    assert stats["total"] == 9

    selected = select_random_questions_scoped(limit=20)
    assert len(selected) == 9
    by_type = {}
    for question in selected:
        by_type.setdefault(question["type"], []).append(question)
    assert set(by_type) == {
        "ordering", "matching", "priority_ranking", "fill_blank", "point_allocation",
    }
    fill = by_type["fill_blank"][0]
    assert fill["word_bank"]
    assert fill["correct_answers"] == ["DPO", "responsable du traitement"]
    assert by_type["priority_ranking"][0]["top_n"] == 2
    assert by_type["point_allocation"][0]["total_points"] == 100

    repeat = add_quiz_to_bank(quiz)
    assert repeat["added"] == 0
    assert repeat["ignored"] == 9
