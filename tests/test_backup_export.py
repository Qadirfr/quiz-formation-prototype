import base64
import hashlib
import io
import json
import sqlite3
import tempfile
import unittest
import zipfile
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from utils import backup_export
from utils.backup_export import APPLICATION_TABLES, BackupExportError, create_backup_archive


def unpack(result):
    with zipfile.ZipFile(io.BytesIO(result.data)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


class BackupSQLiteTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.path = self.root / "history with spaces.db"
        self.mode = patch.object(backup_export, "get_database_mode", return_value="sqlite")
        self.mode.start()
        self.addCleanup(self.mode.stop)
        self.question = {
            "type": "prioritization", "question": "Quel contrôle protège les données ?",
            "correct_answer": ["B", "A"], "custom_metadata": {"équipe": "Été", "nullable": None},
            "context": {"title": "Cas partagé", "text": "Texte intégral et corrigé préservés."},
        }
        self.raw_question = json.dumps(self.question, ensure_ascii=False, indent=3)
        with sqlite3.connect(self.path) as conn:
            conn.executescript("""
                CREATE TABLE saved_quizzes (id INTEGER PRIMARY KEY, title TEXT, quiz_json TEXT);
                CREATE TABLE question_bank (id INTEGER PRIMARY KEY, question_json TEXT, is_active INTEGER,
                                            source_quiz_id INTEGER REFERENCES saved_quizzes(id));
                CREATE TABLE learners (id INTEGER PRIMARY KEY, name TEXT, email TEXT);
                CREATE TABLE quiz_attempts (id INTEGER PRIMARY KEY, learner_id INTEGER REFERENCES learners(id),
                                           quiz_id INTEGER, percentage REAL);
                CREATE TABLE learner_answers (id INTEGER PRIMARY KEY, attempt_id INTEGER REFERENCES quiz_attempts(id),
                                              user_answer_json TEXT, correct_answer_json TEXT,
                                              question_snapshot_json TEXT);
                CREATE TABLE training_sessions (id INTEGER PRIMARY KEY, access_code TEXT, questions_json TEXT);
                CREATE TABLE session_participants (id INTEGER PRIMARY KEY, session_id INTEGER, learner_id INTEGER);
                CREATE TABLE session_answers (id INTEGER PRIMARY KEY, session_id INTEGER, participant_id INTEGER,
                                              learner_id INTEGER, user_answer_json TEXT, score REAL);
                CREATE TABLE question_schema_migration_log (id INTEGER PRIMARY KEY, migration_run_id TEXT,
                    question_id INTEGER, previous_question_json TEXT, new_question_json TEXT);
            """)
            conn.execute("INSERT INTO saved_quizzes VALUES (9, ?, ?)", ("Formation été RGPD", self.raw_question))
            conn.execute("INSERT INTO question_bank VALUES (101, ?, 0, 9)", (self.raw_question,))
            conn.execute("INSERT INTO learners VALUES (4, 'Élodie', 'test@example.invalid')")
            conn.execute("INSERT INTO quiz_attempts VALUES (7, 4, 9, 62.5)")
            conn.execute("INSERT INTO learner_answers VALUES (12, 7, ?, ?, ?)",
                         ('["A"]', '["B", "A"]', self.raw_question))
            conn.execute("INSERT INTO training_sessions VALUES (2, 'SESSION-TEST', ?)",
                         (json.dumps([self.question], ensure_ascii=False),))
            conn.execute("INSERT INTO session_participants VALUES (6, 2, 4)")
            conn.execute("INSERT INTO session_answers VALUES (15, 2, 6, 4, '\"A\"', 0.5)")
            conn.execute("INSERT INTO question_schema_migration_log VALUES (3, 'migration-test', 101, ?, ?)",
                         ('{"type": "case"}', self.raw_question))

    def export(self, **kwargs):
        return create_backup_archive(sqlite_path=self.path, project_root=self.root, **kwargs)

    def set_question(self, question):
        with sqlite3.connect(self.path) as conn:
            conn.execute("UPDATE question_bank SET question_json = ? WHERE id=101",
                         (json.dumps(question, ensure_ascii=False),))

    def test_all_tables_relations_and_exact_json_are_preserved_without_writes(self):
        before = self.path.read_bytes()
        result = self.export()
        files = unpack(result)
        self.assertEqual(self.path.read_bytes(), before)
        manifest = json.loads(files["manifest.json"])
        self.assertEqual(manifest, result.manifest)
        self.assertEqual(manifest["row_counts"], {table: 1 for table in APPLICATION_TABLES})
        self.assertEqual(manifest["total_rows"], 9)
        self.assertEqual(manifest["database_engine"], "sqlite")
        self.assertTrue(manifest["all_expected_tables_present"])
        self.assertFalse(manifest["restoration_supported"])
        for table in manifest["tables"]:
            self.assertEqual(table["sha256"], hashlib.sha256(files[table["path"]]).hexdigest())
        bank = json.loads(files["tables/question_bank.json"])["rows"][0]
        self.assertEqual(bank["question_json"], self.raw_question)
        self.assertEqual(bank["is_active"], 0)
        self.assertEqual(bank["source_quiz_id"], 9)
        answer = json.loads(files["tables/learner_answers.json"])["rows"][0]
        self.assertEqual(answer["attempt_id"], 7)
        self.assertEqual(answer["question_snapshot_json"], self.raw_question)
        self.assertEqual(json.loads(files["tables/learners.json"])["rows"][0]["name"], "Élodie")
        self.assertEqual(json.loads(files["tables/training_sessions.json"])["rows"][0]["access_code"], "SESSION-TEST")
        self.assertEqual(json.loads(files["tables/question_schema_migration_log.json"])["rows"][0]["previous_question_json"], '{"type": "case"}')
        self.assertTrue(result.filename.endswith(".zip"))

    def test_more_than_one_fetch_batch_has_no_silent_record_limit(self):
        with sqlite3.connect(self.path) as conn:
            conn.executemany("INSERT INTO question_bank VALUES (?, ?, 1, 9)",
                             ((1000 + i, self.raw_question) for i in range(1205)))
        result = self.export()
        rows = json.loads(unpack(result)["tables/question_bank.json"])["rows"]
        self.assertEqual(result.manifest["row_counts"]["question_bank"], 1206)
        self.assertEqual(len(rows), 1206)
        self.assertEqual(rows[-1]["id"], 2204)

    def test_missing_database_is_never_created(self):
        absent = self.root / "absent" / "history.db"
        with self.assertRaisesRegex(BackupExportError, "n'existe pas"):
            create_backup_archive(sqlite_path=absent, project_root=self.root)
        self.assertFalse(absent.exists())
        self.assertFalse(absent.parent.exists())

    def test_unknown_tables_are_not_exported_and_absent_log_is_recorded(self):
        with sqlite3.connect(self.path) as conn:
            conn.execute("DROP TABLE question_schema_migration_log")
            conn.execute("CREATE TABLE server_secrets (secret TEXT)")
            conn.execute("INSERT INTO server_secrets VALUES ('PRIVATE-DATABASE-PASSWORD')")
        result = self.export()
        files = unpack(result)
        self.assertNotIn("tables/server_secrets.json", files)
        self.assertNotIn(b"PRIVATE-DATABASE-PASSWORD", b"\n".join(files.values()))
        self.assertEqual(result.manifest["missing_tables"], ["question_schema_migration_log"])
        self.assertEqual(result.manifest["unrecognized_tables_not_exported"], ["server_secrets"])
        self.assertTrue(result.manifest["all_expected_tables_present"])

    def test_absent_required_table_is_explicit(self):
        with sqlite3.connect(self.path) as conn:
            conn.execute("DROP TABLE session_answers")
        result = self.export()
        self.assertFalse(result.manifest["all_expected_tables_present"])
        self.assertIn("session_answers", result.manifest["missing_tables"])
        self.assertTrue(result.manifest["warnings"])

    def test_optional_migration_log_absence_does_not_warn_about_missing_tables(self):
        with sqlite3.connect(self.path) as conn:
            conn.execute("DROP TABLE question_schema_migration_log")
        result = self.export()
        self.assertTrue(result.manifest["all_expected_tables_present"])
        self.assertEqual(result.manifest["warnings"], [])

    def test_no_application_table_is_rejected(self):
        other = self.root / "other.db"
        with sqlite3.connect(other) as conn:
            conn.execute("CREATE TABLE unrelated (id INTEGER)")
        with self.assertRaisesRegex(BackupExportError, "Aucune table Quiz Formation"):
            create_backup_archive(sqlite_path=other)

    def test_empty_tables_have_zero_rows_in_valid_json(self):
        with sqlite3.connect(self.path) as conn:
            for table in APPLICATION_TABLES:
                conn.execute('DELETE FROM "' + table + '"')
        result = self.export()
        self.assertEqual(result.manifest["total_rows"], 0)
        for table in APPLICATION_TABLES:
            self.assertEqual(json.loads(unpack(result)["tables/" + table + ".json"])["rows"], [])

    def test_size_limit_aborts_instead_of_returning_partial_archive(self):
        before = self.path.read_bytes()
        with self.assertRaisesRegex(BackupExportError, "limite de taille"):
            self.export(max_uncompressed_bytes=100)
        self.assertEqual(self.path.read_bytes(), before)
        for invalid in (0, -1, True, 10.5):
            with self.assertRaises(BackupExportError):
                self.export(max_uncompressed_bytes=invalid)

    def test_local_embedded_context_and_remote_media_are_accounted_for(self):
        (self.root / "assets").mkdir()
        image = b"\x89PNG\r\nexample-bytes"
        (self.root / "assets" / "été.png").write_bytes(image)
        data_uri = "data:image/png;base64," + base64.b64encode(image).decode()
        remote = "https://example.invalid/image.png?version=1"
        question = {
            "media": ["assets/été.png", {"url": remote}, {"url": data_uri}],
            "context": {"media": {"src": "assets/../assets/été.png"}},
            "image_url": "assets/missing.png",
        }
        self.set_question(question)
        result = self.export()
        files = unpack(result)
        self.assertEqual(files["media/assets/été.png"], image)
        self.assertEqual(result.manifest["media"]["packed_count"], 1)
        self.assertEqual(result.manifest["media"]["embedded_count"], 1)
        self.assertEqual(result.manifest["media"]["external_count"], 1)
        self.assertEqual(result.manifest["media"]["unresolved_count"], 2)
        self.assertFalse(result.manifest["media"]["all_referenced_media_included"])
        raw = json.loads(files["tables/question_bank.json"])["rows"][0]["question_json"]
        self.assertEqual(json.loads(raw), question)
        self.assertIn(data_uri, raw)
        self.assertNotIn(data_uri, files["manifest.json"].decode())

    def test_media_cannot_export_secrets_traversal_or_external_symlinks(self):
        (self.root / "assets").mkdir()
        (self.root / "media").mkdir()
        (self.root / ".streamlit").mkdir()
        (self.root / ".env").write_text("PRIVATE-ENV-SECRET")
        (self.root / ".streamlit" / "secrets.toml").write_text("PRIVATE-STREAMLIT-SECRET")
        (self.root / "media" / "secrets.txt").write_text("PRIVATE-MEDIA-SECRET")
        (self.root / "assets" / "database.db").write_bytes(b"PRIVATE-SQLITE-SECRET")
        with tempfile.TemporaryDirectory() as outside:
            external_file = Path(outside) / "external.png"
            external_file.write_bytes(b"PRIVATE-EXTERNAL-SECRET")
            (self.root / "assets" / "shortcut.png").symlink_to(external_file)
            self.set_question({"media": [
                ".env", ".streamlit/secrets.toml", "assets/../.env", "media/secrets.txt",
                "assets/database.db", str(external_file), "assets/shortcut.png",
                external_file.as_uri(), "C:\\private\\file.png", "assets/%2e%2e/.env",
            ]})
            result = self.export()
        files = unpack(result)
        self.assertEqual(result.manifest["media"]["packed_count"], 0)
        self.assertFalse(any(name.startswith("media/") for name in files))
        self.assertNotIn(b"PRIVATE-", b"\n".join(files.values()))
        self.assertEqual(result.manifest["media"]["unresolved_count"], 10)

    def test_invalid_media_uri_is_recorded_without_discarding_data(self):
        self.set_question({"media": "https://[invalid"})
        result = self.export()
        self.assertEqual(result.manifest["media"]["references"][0]["status"], "invalid_reference")
        self.assertEqual(result.manifest["row_counts"]["question_bank"], 1)

    def test_media_root_symlink_cannot_escape_project(self):
        with tempfile.TemporaryDirectory() as outside:
            (Path(outside) / "external.png").write_bytes(b"PRIVATE-EXTERNAL-SECRET")
            (self.root / "assets").symlink_to(outside, target_is_directory=True)
            self.set_question({"media": "assets/external.png"})
            result = self.export()
        self.assertEqual(result.manifest["media"]["packed_count"], 0)
        self.assertEqual(result.manifest["media"]["references"][0]["status"], "outside_media_directories")
        self.assertNotIn(b"PRIVATE-", b"\n".join(unpack(result).values()))

    def test_blobs_and_nonfinite_floats_are_losslessly_tagged(self):
        with sqlite3.connect(self.path) as conn:
            conn.execute("ALTER TABLE question_bank ADD COLUMN raw_blob BLOB")
            conn.execute("ALTER TABLE question_bank ADD COLUMN special_score REAL")
            conn.execute("UPDATE question_bank SET raw_blob=?, special_score=?", (b"\xff\x00binary", float("inf")))
        row = json.loads(unpack(self.export())["tables/question_bank.json"])["rows"][0]
        self.assertEqual(base64.b64decode(row["raw_blob"]["value"]), b"\xff\x00binary")
        self.assertEqual(row["special_score"], {"__quiz_backup_type__": "float", "value": "inf"})

    def test_all_tables_share_one_sqlite_snapshot_during_concurrent_write(self):
        with sqlite3.connect(self.path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
        original = backup_export._write_table

        def write_then_change(*args, **kwargs):
            result = original(*args, **kwargs)
            if result["name"] == "saved_quizzes":
                with sqlite3.connect(self.path) as writer:
                    writer.execute("UPDATE question_bank SET question_json='changed later'")
            return result

        with patch.object(backup_export, "_write_table", side_effect=write_then_change):
            result = self.export()
        bank = json.loads(unpack(result)["tables/question_bank.json"])["rows"][0]
        self.assertEqual(bank["question_json"], self.raw_question)
        with sqlite3.connect(self.path) as conn:
            self.assertEqual(conn.execute("SELECT question_json FROM question_bank").fetchone()[0], "changed later")


class _PostgresCursor:
    def __init__(self, connection, name=None):
        self.connection = connection
        self.name = name
        self.result = []
        self.offset = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=()):
        self.connection.commands.append((sql, params, self.name))
        self.offset = 0
        if sql.startswith("SET TRANSACTION"):
            self.result = []
        elif "information_schema.tables" in sql:
            self.result = [{"table_name": "question_bank"}]
        elif "row_security_active" in sql:
            self.result = [{"active": self.connection.rls, "all_columns_readable": self.connection.full_table_access}]
        elif "information_schema.columns" in sql:
            self.result = [
                {"column_name": name, "data_type": kind, "is_nullable": "YES", "column_default": None, "udt_name": kind}
                for name, kind in [("id", "bigint"), ("question_json", "jsonb"), ("score", "numeric"), ("created_at", "timestamptz")]
            ]
        elif ' FROM public."question_bank"' in sql:
            if '"question_json"::text AS "question_json"' not in sql:
                raise AssertionError("JSONB must be returned as server text without float conversion")
            self.result = [self.connection.row]
        else:
            raise AssertionError("Unexpected SQL: " + sql)

    def fetchall(self):
        return self.result

    def fetchone(self):
        return self.result[0]

    def fetchmany(self, size):
        result = self.result[self.offset:self.offset + size]
        self.offset += len(result)
        return result


class _PostgresConnection:
    def __init__(self, rls=False, full_table_access=True):
        self.rls = rls
        self.full_table_access = full_table_access
        self.commands = []
        self.events = []
        self.row = {
            "id": 9223372036854775806,
            "question_json": '{"context": {"text": "Évaluation"}, "correct_answer": ["A", "B"], '
                             '"weight": 0.12345678901234567890123456789, '
                             '"media": {"url": "data:image/png;base64,ZmFrZQ=="}}',
            "score": Decimal("0.12345678901234567890123456789"),
            "created_at": datetime(2026, 11, 21, 15, 30, tzinfo=timezone.utc),
        }

    def cursor(self, name=None):
        return _PostgresCursor(self, name)

    @contextmanager
    def transaction(self):
        self.events.append("begin")
        try:
            yield self
        except Exception:
            self.events.append("rollback")
            raise
        else:
            self.events.append("end")


class BackupPostgresAdapterTests(unittest.TestCase):
    def export_from(self, conn):
        @contextmanager
        def connection():
            yield conn
        with patch.object(backup_export, "get_database_mode", return_value="postgres"), \
             patch.object(backup_export, "get_postgres_connection", side_effect=connection):
            return create_backup_archive()

    def test_postgres_transaction_server_cursor_and_precise_values(self):
        conn = _PostgresConnection()
        result = self.export_from(conn)
        self.assertEqual(conn.events, ["begin", "end"])
        self.assertEqual(conn.commands[0][0], "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        self.assertTrue(any(name == "quiz_formation_backup_question_bank" for _, _, name in conn.commands))
        row = json.loads(unpack(result)["tables/question_bank.json"])["rows"][0]
        self.assertEqual(row["id"], conn.row["id"])
        self.assertEqual(row["question_json"], conn.row["question_json"])
        self.assertEqual(result.manifest["media"]["embedded_count"], 1)
        self.assertIn("0.12345678901234567890123456789", row["question_json"])
        self.assertEqual(row["score"], {"__quiz_backup_type__": "decimal", "value": str(conn.row["score"])})
        self.assertEqual(row["created_at"]["value"], "2026-11-21T15:30:00+00:00")
        self.assertEqual(result.manifest["database_engine"], "postgres")

    def test_postgres_rls_refuses_a_silently_partial_backup(self):
        conn = _PostgresConnection(rls=True)
        with self.assertRaisesRegex(BackupExportError, "masquer des lignes"):
            self.export_from(conn)
        self.assertEqual(conn.events, ["begin", "rollback"])
        self.assertFalse(any(' FROM public."question_bank"' in sql for sql, _, _ in conn.commands))

    def test_postgres_column_only_permissions_refuse_incomplete_schema(self):
        conn = _PostgresConnection(full_table_access=False)
        with self.assertRaisesRegex(BackupExportError, "toutes les colonnes"):
            self.export_from(conn)
        self.assertEqual(conn.events, ["begin", "rollback"])
        self.assertFalse(any(' FROM public."question_bank"' in sql for sql, _, _ in conn.commands))

    def test_connection_error_message_does_not_expose_credentials(self):
        with patch.object(backup_export, "get_database_mode", return_value="postgres"), \
             patch.object(backup_export, "get_postgres_connection", side_effect=RuntimeError("password=PRIVATE host=hidden")):
            with self.assertRaises(BackupExportError) as error:
                create_backup_archive()
        self.assertNotIn("PRIVATE", str(error.exception))
        self.assertNotIn("hidden", str(error.exception))
        self.assertIsInstance(error.exception.__cause__, RuntimeError)


if __name__ == "__main__":
    unittest.main()
