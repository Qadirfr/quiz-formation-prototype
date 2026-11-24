"""Smoke-test the actual V23 trainer interface with a disposable SQLite database."""

from pathlib import Path
from streamlit.testing.v1 import AppTest


def test_trainer_can_preview_and_download_interactive_templates(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_DATABASE_MODE", "sqlite")
    monkeypatch.setenv("SQLITE_DB_PATH", str(tmp_path / "v23-test.db"))
    monkeypatch.setenv("QUIZ_TRAINER_PASSWORD", "trainer-test-only")
    monkeypatch.setenv("QUIZ_LEARNER_CODE", "LEARNER-TEST")
    app_file = Path(__file__).resolve().parents[1] / "app.py"
    at = AppTest.from_file(str(app_file), default_timeout=60)
    at.secrets = {}
    at.run()
    assert not at.exception, [e.message for e in at.exception]
    login = next(item for item in at.text_input if item.key == "login_trainer_password")
    login.input("trainer-test-only").run()
    enter = next(item for item in at.button if item.label == "Entrer comme formateur")
    enter.click().run()
    assert not at.exception, [e.message for e in at.exception]
    assert any(t.value == "Espace formateur" for t in at.title)
    assert any("Modèles d\u0027import des exercices interactifs" in m.value for m in at.markdown)
