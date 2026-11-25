"""Lot 4 trainer and learner wiring is compatible with V23 navigation."""
import ast
from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_hotspot_widgets_exposed_in_all_passation_paths():
    source = (Path(__file__).resolve().parents[1] / "app.py").read_text("utf-8")
    tree = ast.parse(source)
    defs = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    for name in ("render_interactive_preview", "render_test_question", "render_session_question"):
        calls = {
            node.func.id for node in ast.walk(defs[name])
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert "render_visual" in calls, name
    calls = {
        node.func.id for node in ast.walk(defs["evaluate_answer"])
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "evaluate_visual" in calls
    code = ast.get_source_segment(source, defs["has_interactive_card_activity"])
    assert '"image_hotspots"' in code


def test_visual_trainer_screen_does_not_need_supabase(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_DATABASE_MODE", "sqlite")
    monkeypatch.setenv("SQLITE_DB_PATH", str(tmp_path / "v23-visual-ui.db"))
    monkeypatch.setenv("QUIZ_TRAINER_PASSWORD", "visual-test-only")
    monkeypatch.setenv("QUIZ_LEARNER_CODE", "VISUAL-TEST")
    from utils.database import init_quiz_history_db
    from utils.learner_db import init_learner_db
    from utils.question_bank import init_question_bank_db
    from utils.session_db import init_session_db
    for init in (init_quiz_history_db, init_learner_db, init_question_bank_db, init_session_db):
        init.cache_clear()

    path = Path(__file__).resolve().parents[1] / "app.py"
    app = AppTest.from_file(str(path), default_timeout=60)
    app.secrets = {}
    app.run()
    assert not app.exception, [item.message for item in app.exception]
    next(x for x in app.text_input if x.key == "login_trainer_password").input(
        "visual-test-only"
    ).run()
    next(x for x in app.button if x.label == "Entrer comme formateur").click().run()
    assert not app.exception, [item.message for item in app.exception]
    assert any(x.value == "Espace formateur" for x in app.title)
    assert any(x.key == "trainer_visual_demo_index" for x in app.selectbox)

    editor = next(x for x in app.selectbox if x.key == "manual_question_type")
    editor.select("image_hotspots").run()
    assert not app.exception, [item.message for item in app.exception]
    assert any("Choisis d'abord une illustration" in x.value for x in app.info)
