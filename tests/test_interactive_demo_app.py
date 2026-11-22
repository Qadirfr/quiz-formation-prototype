"""The standalone V24 preview must start without PostgreSQL or credentials."""

from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_demo_app_opens_without_database(monkeypatch):
    monkeypatch.setenv("APP_DATABASE_MODE", "postgres")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("QUIZ_TRAINER_PASSWORD", raising=False)
    app_file = Path(__file__).resolve().parents[1] / "interactive_demo_app.py"
    app = AppTest.from_file(str(app_file), default_timeout=30)
    app.secrets = {}
    app.run()
    assert not app.exception, [element.value for element in app.exception]
    assert any("ateliers" in element.value.casefold() for element in app.title)
    assert any("question" in element.label.lower() for element in app.selectbox)
