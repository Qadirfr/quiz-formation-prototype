"""Trainer backup and access regressions, using disposable local databases only.

Run with ``python -m pytest tests/test_app_backup.py`` from the project root.
AppTest renders download buttons but cannot click them; these tests inspect the
download widget and validate the exact archive bytes held by the application.
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import sqlite3
import sys
from unittest.mock import Mock
import zipfile

import pytest
import requests
import streamlit as st
from streamlit.testing.v1 import AppTest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from utils import backup_export, database, learner_db, question_bank, session_db


TRAINER_PASSWORD = "AppTest-Trainer-Only-2026"
LEARNER_CODE = "APPTEST-LEARNER-ONLY"
TEST_QUIZ = {
    "quiz_title": "Quiz temporaire de contrôle interne",
    "questions": [
        {
            "type": "single_choice",
            "question": "Quel élément permet de vérifier un contrôle ?",
            "options": ["Une preuve documentée", "Une simple supposition"],
            "correct_answer": "A",
            "explanation": "Une preuve documentée permet de vérifier le contrôle.",
            "remediation": "Revoir la notion de preuve.",
        }
    ],
}


def _clear_database_caches() -> None:
    # The app also has a resource cache around these cached initializers. Both
    # layers must be reset so every test initializes its own SQLite database.
    st.cache_resource.clear()
    for initialize in (
        database.init_quiz_history_db,
        learner_db.init_learner_db,
        question_bank.init_question_bank_db,
        session_db.init_session_db,
    ):
        initialize.cache_clear()


@pytest.fixture
def app_factory(tmp_path, monkeypatch):
    monkeypatch.chdir(PROJECT_ROOT)
    monkeypatch.setenv("APP_DATABASE_MODE", "sqlite")
    monkeypatch.setenv("SQLITE_DB_PATH", str(tmp_path / "app-test.db"))
    monkeypatch.setenv("QUIZ_TRAINER_PASSWORD", TRAINER_PASSWORD)
    monkeypatch.setenv("QUIZ_LEARNER_CODE", LEARNER_CODE)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    def reject_network(*args, **kwargs):
        raise AssertionError("AppTest must not contact Ollama or external services")

    monkeypatch.setattr(requests.sessions.Session, "request", reject_network)
    _clear_database_caches()

    def make_app(*, secrets=None):
        app = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=30)
        # Explicit values prevent these tests from using any real secret file.
        app.secrets = {} if secrets is None else secrets
        app.run()
        _assert_no_exception(app)
        return app

    yield make_app
    _clear_database_caches()


def _assert_no_exception(app: AppTest) -> None:
    assert not app.exception, [element.value for element in app.exception]


def _click(app: AppTest, label: str) -> AppTest:
    next(button for button in app.button if button.label == label).click().run()
    _assert_no_exception(app)
    return app


def _login_trainer(app: AppTest, password: str = TRAINER_PASSWORD) -> AppTest:
    app.text_input(key="login_trainer_password").input(password)
    _click(app, "Entrer comme formateur")
    return app


def _login_learner(app: AppTest) -> AppTest:
    app.text_input(key="login_learner_name").input("Apprenant de test")
    app.text_input(key="login_learner_email").input("learner@example.invalid")
    app.text_input(key="login_learner_code").input(LEARNER_CODE)
    return _click(app, "Entrer comme apprenant")


def _archive(app: AppTest):
    if "full_backup_archive" in app.session_state:
        return app.session_state["full_backup_archive"]
    return None


def _backup_downloads(app: AppTest):
    return [
        element
        for element in app.get("download_button")
        if element.proto.id.endswith("-download_full_backup")
    ]


def _prepare_backup(app: AppTest) -> AppTest:
    app.button(key="prepare_full_backup").click().run()
    _assert_no_exception(app)
    return app


def test_trainer_login_uses_environment_password(app_factory):
    app = _login_trainer(app_factory())
    assert app.session_state["role"] == "trainer"
    assert "7. Export" in [tab.label for tab in app.tabs]
    assert app.button(key="prepare_full_backup") is not None


def test_trainer_login_reads_streamlit_secret(app_factory, monkeypatch):
    monkeypatch.delenv("QUIZ_TRAINER_PASSWORD")
    secret_password = "Explicit-Test-Streamlit-Secret"
    app = app_factory(secrets={"QUIZ_TRAINER_PASSWORD": secret_password})
    _login_trainer(app, secret_password)
    assert app.session_state["role"] == "trainer"


def test_missing_trainer_password_refuses_previous_default(app_factory, monkeypatch):
    monkeypatch.delenv("QUIZ_TRAINER_PASSWORD")
    app = app_factory()
    assert any("QUIZ_TRAINER_PASSWORD" in element.value for element in app.info)
    _login_trainer(app, "formateur123")
    assert app.session_state["role"] is None
    assert any("configur" in element.value.lower() for element in app.error)
    assert not any(button.key == "prepare_full_backup" for button in app.button)


def test_backup_is_only_prepared_on_click_and_includes_stored_data(
    app_factory, monkeypatch
):
    export = Mock(wraps=backup_export.create_backup_archive)
    monkeypatch.setattr(backup_export, "create_backup_archive", export)
    app = _login_trainer(app_factory())
    quiz_id = database.save_quiz(TEST_QUIZ)
    learner = learner_db.create_or_get_learner(
        "Sauvegarde Test", "backup@example.invalid", "Groupe temporaire"
    )
    assert app.session_state["quiz"] is None
    export.assert_not_called()
    assert _archive(app) is None
    assert not _backup_downloads(app)

    _prepare_backup(app)
    export.assert_called_once()
    archive = _archive(app)
    assert archive is not None
    assert archive.filename.endswith(".zip")
    assert archive.manifest["database_engine"] == "sqlite"
    assert archive.manifest["row_counts"]["saved_quizzes"] == 1
    assert archive.manifest["row_counts"]["learners"] == 1
    with zipfile.ZipFile(io.BytesIO(archive.data)) as zip_file:
        assert zip_file.testzip() is None
        assert json.loads(zip_file.read("manifest.json")) == archive.manifest
        quizzes = json.loads(zip_file.read("tables/saved_quizzes.json"))["rows"]
        learners = json.loads(zip_file.read("tables/learners.json"))["rows"]
    assert quizzes[0]["id"] == quiz_id
    assert quizzes[0]["title"] == TEST_QUIZ["quiz_title"]
    assert learners[0]["id"] == learner["id"]
    assert learners[0]["email"] == "backup@example.invalid"
    counts = next(
        frame.value
        for frame in app.dataframe
        if set(("Données", "Lignes exportées")).issubset(frame.value.columns)
    ).set_index("Données")["Lignes exportées"]
    assert counts["Quiz sauvegardés"] == 1
    assert counts["Apprenants"] == 1

    download, = _backup_downloads(app)
    assert download.proto.url
    assert not download.proto.disabled
    # In particular, a rerun with populated history/session selectors must keep
    # the prepared download and must not export the database for a second time.
    app.run()
    _assert_no_exception(app)
    export.assert_called_once()
    assert _archive(app).data == archive.data


def test_empty_database_can_be_backed_up_without_loading_quiz(app_factory, monkeypatch):
    export = Mock(wraps=backup_export.create_backup_archive)
    monkeypatch.setattr(backup_export, "create_backup_archive", export)
    app = _login_trainer(app_factory())
    _prepare_backup(app)
    archive = _archive(app)
    assert archive is not None
    assert archive.manifest["total_rows"] == 0
    assert _backup_downloads(app)
    # A normal rerun reuses the archive without making another database copy.
    app.run()
    _assert_no_exception(app)
    export.assert_called_once()
    assert _archive(app).data == archive.data


def test_backup_can_be_explicitly_cleared(app_factory):
    app = _login_trainer(app_factory())
    _prepare_backup(app)
    assert _archive(app) is not None
    app.button(key="clear_full_backup").click().run()
    _assert_no_exception(app)
    assert _archive(app) is None
    assert not _backup_downloads(app)
    assert app.session_state["role"] == "trainer"


def test_logout_clears_backup_and_learner_cannot_access_it(app_factory):
    app = _login_trainer(app_factory())
    _prepare_backup(app)
    assert _archive(app) is not None
    _click(app, "Se déconnecter")
    assert app.session_state["role"] is None
    assert _archive(app) is None
    assert not _backup_downloads(app)

    _login_learner(app)
    assert app.session_state["role"] == "learner"
    assert _archive(app) is None
    assert not any(button.key == "prepare_full_backup" for button in app.button)
    assert not _backup_downloads(app)


def test_removing_password_revokes_trainer_access_and_backup(app_factory, monkeypatch):
    app = _login_trainer(app_factory())
    _prepare_backup(app)
    assert _archive(app) is not None
    monkeypatch.delenv("QUIZ_TRAINER_PASSWORD")
    app.run()
    _assert_no_exception(app)
    assert app.session_state["role"] is None
    assert _archive(app) is None
    assert not _backup_downloads(app)
    assert any("QUIZ_TRAINER_PASSWORD" in element.value for element in app.info)


@pytest.mark.parametrize("error_type", [backup_export.BackupExportError, RuntimeError])
def test_failed_export_clears_previous_archive_and_hides_connection_details(
    app_factory, monkeypatch, error_type
):
    app = _login_trainer(app_factory())
    _prepare_backup(app)
    assert _archive(app) is not None
    secret_marker = "must-not-appear-in-interface"
    # BackupExportError is the backend's public, sanitized error type. Unexpected
    # errors are untrusted and must never be printed verbatim by the UI.
    safe_message = "La sauvegarde dépasse la limite de taille autorisée."
    message = (
        safe_message
        if error_type is backup_export.BackupExportError
        else f"postgresql://test:{secret_marker}@db.example.invalid/quiz"
    )
    export = Mock(side_effect=error_type(message))
    monkeypatch.setattr(backup_export, "create_backup_archive", export)
    _prepare_backup(app)
    export.assert_called_once()
    assert _archive(app) is None
    assert not _backup_downloads(app)
    assert app.error
    visible_text = "\n".join(
        str(element.value)
        for kind in ("error", "warning", "info", "caption", "markdown")
        for element in app.get(kind)
    )
    assert secret_marker not in visible_text
    assert "postgresql://" not in visible_text
    if error_type is backup_export.BackupExportError:
        assert safe_message in visible_text


def test_demo_generation_still_produces_a_quiz(app_factory):
    app = _login_trainer(app_factory())
    next(
        field for field in app.text_area if field.label == "Ou colle ton contenu ici"
    ).input(
        "Le contrôle interne contribue à maîtriser les risques d’une organisation. "
        "Les contrôles répondent à des objectifs clairement définis. "
        "Une preuve documentée permet de vérifier leur réalisation. "
        "Un audit examine la conception et le fonctionnement des contrôles. "
        "Le suivi des actions vérifie leur efficacité."
    )
    _click(app, "Générer le quiz")
    assert len(app.session_state["quiz"]["questions"]) == 5


def test_learner_can_complete_a_prepared_quiz(app_factory):
    app = app_factory()
    quiz_id = database.save_quiz(TEST_QUIZ)
    _login_learner(app)
    _click(app, "Démarrer ce quiz")
    assert app.session_state["active_attempt_id"] is not None
    app.radio(key="test_answer_1").set_value("A. Une preuve documentée")
    _click(app, "Valider mes réponses")
    with sqlite3.connect(os.environ["SQLITE_DB_PATH"]) as connection:
        attempt = connection.execute(
            "SELECT quiz_id, score, max_score, percentage FROM quiz_attempts"
        ).fetchone()
        answer_count = connection.execute(
            "SELECT COUNT(*) FROM learner_answers"
        ).fetchone()[0]
    assert attempt == (quiz_id, 1.0, 1.0, 100.0)
    assert answer_count == 1
