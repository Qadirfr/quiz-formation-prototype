"""Lot 3: bank persistence and trainer preview on the existing V23 Streamlit app."""
from pathlib import Path
import io

from streamlit.testing.v1 import AppTest

from utils.scenario_templates import scenario_xlsx_bytes
from utils.table_import import read_quiz_table, validate_imported_quiz


class Upload(io.BytesIO):
    def __init__(self, payload):
        super().__init__(payload)
        self.name = "scenarios_lot3.xlsx"


def test_scenarios_preserved_in_existing_sqlite_question_bank(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_DATABASE_MODE", "sqlite")
    monkeypatch.setenv("SQLITE_DB_PATH", str(tmp_path / "lot3.db"))
    from utils.question_bank import (
        add_quiz_to_bank, get_question_bank_stats, init_question_bank_db,
        select_random_questions_scoped,
    )
    init_question_bank_db.cache_clear()
    quiz = read_quiz_table(Upload(scenario_xlsx_bytes()))
    assert validate_imported_quiz(quiz)["valid"]
    result = add_quiz_to_bank(quiz)
    assert result["added"] == 2, result
    assert get_question_bank_stats()["total"] == 2
    imported = select_random_questions_scoped(limit=20)
    assert len(imported) == 2
    assert all(q["type"] == "branching_scenario" for q in imported)
    assert all(len(q["scenario_nodes"]) == 3 for q in imported)
    assert all(q.get("scenario_start") == "S1" for q in imported)
    repeat = add_quiz_to_bank(quiz)
    assert repeat["added"] == 0
    assert repeat["ignored"] == 2


def test_trainer_can_play_branching_preview_without_database_writes(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_DATABASE_MODE", "sqlite")
    monkeypatch.setenv("SQLITE_DB_PATH", str(tmp_path / "trainer-lot3.db"))
    monkeypatch.setenv("QUIZ_TRAINER_PASSWORD", "test-trainer-only")
    monkeypatch.setenv("QUIZ_LEARNER_CODE", "TEST-LEARNER-ONLY")
    path = Path(__file__).resolve().parents[1] / "app.py"
    at = AppTest.from_file(str(path), default_timeout=60)
    at.secrets = {}
    at.run()
    assert not at.exception, [e.message for e in at.exception]
    next(x for x in at.text_input if x.key == "login_trainer_password").input(
        "test-trainer-only"
    ).run()
    next(x for x in at.button if x.label == "Entrer comme formateur").click().run()
    assert not at.exception, [e.message for e in at.exception]
    assert any(t.value == "Espace formateur" for t in at.title)
    first = next(
        b for b in at.button
        if b.key == "trainer_scenario_demo_0_scenario_node_S1_choice_A"
    )
    first.click().run()
    assert not at.exception, [e.message for e in at.exception]
    second = next(
        b for b in at.button
        if b.key == "trainer_scenario_demo_0_scenario_node_S2_choice_A"
    )
    second.click().run()
    assert not at.exception, [e.message for e in at.exception]
    assert any("parcours est terminé" in s.message for s in at.success)
    next(
        b for b in at.button
        if b.key == "trainer_scenario_demo_0_validate"
    ).click().run()
    assert not at.exception, [e.message for e in at.exception]
    assert any("Réponse correcte" in item.message for item in at.success)
