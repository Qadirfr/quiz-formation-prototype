"""Read-only, portable exports of Quiz Formation's persisted application data.

The archive is a data export, not a PostgreSQL server backup or an automatic
restore package. JSON text is preserved; PostgreSQL JSON/JSONB use the server's
text representation to avoid float conversion. Uploaded data URIs remain
embedded in those values. Remote media are never fetched.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import math
import os
import sqlite3
import stat
import zipfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple
from urllib.parse import unquote, urlsplit
from uuid import UUID

from utils.db_runtime import (
    PROJECT_ROOT,
    get_database_mode,
    get_postgres_connection,
    get_sqlite_path,
)


APPLICATION_TABLES = (
    "saved_quizzes",
    "question_bank",
    "learners",
    "quiz_attempts",
    "learner_answers",
    "training_sessions",
    "session_participants",
    "session_answers",
    "question_schema_migration_log",
)
OPTIONAL_TABLES = frozenset({"question_schema_migration_log"})
MEDIA_DIRECTORIES = ("assets", "media", "uploads", "data/media", "data/uploads")
MEDIA_EXTENSIONS = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".tif", ".tiff",
    ".avif", ".ico", ".mp3", ".wav", ".ogg", ".m4a", ".flac", ".mp4", ".webm",
    ".mov", ".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx", ".csv", ".txt",
})
DEFAULT_MAX_UNCOMPRESSED_BYTES = 128 * 1024 * 1024
FORMAT_VERSION = 1


class BackupExportError(RuntimeError):
    """A safe, actionable export error without connection credentials."""


@dataclass(frozen=True)
class BackupArchive:
    data: bytes
    filename: str
    manifest: Dict[str, Any]


class _Budget:
    def __init__(self, maximum: int) -> None:
        if isinstance(maximum, bool) or not isinstance(maximum, int) or maximum <= 0:
            raise BackupExportError("La limite de taille doit être un entier strictement positif.")
        self.maximum = maximum
        self.used = 0

    def consume(self, size: int) -> None:
        if self.used + size > self.maximum:
            raise BackupExportError(
                "La sauvegarde dépasse la limite de taille autorisée. "
                "Aucune archive partielle n'a été produite."
            )
        self.used += size


def _json_value(value: Any) -> Any:
    """Keep precise non-JSON scalars in an explicit, documented envelope."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if math.isfinite(value):
            return value
        return {"__quiz_backup_type__": "float", "value": repr(value)}
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, Decimal):
        return {"__quiz_backup_type__": "decimal", "value": str(value)}
    if isinstance(value, datetime):
        return {"__quiz_backup_type__": "datetime", "value": value.isoformat()}
    if isinstance(value, date):
        return {"__quiz_backup_type__": "date", "value": value.isoformat()}
    if isinstance(value, time):
        return {"__quiz_backup_type__": "time", "value": value.isoformat()}
    if isinstance(value, UUID):
        return {"__quiz_backup_type__": "uuid", "value": str(value)}
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {
            "__quiz_backup_type__": "bytes",
            "encoding": "base64",
            "value": base64.b64encode(bytes(value)).decode("ascii"),
        }
    raise BackupExportError(
        "La base contient un type de donnée non pris en charge. "
        "L'export est arrêté pour éviter une conversion avec perte."
    )


def _json_bytes(value: Any) -> bytes:
    return json.dumps(
        _json_value(value), ensure_ascii=False, allow_nan=False, separators=(",", ":")
    ).encode("utf-8")


def _safe_table(table: str, mode: str) -> str:
    # No user-provided identifier may become part of a SQL statement.
    if table not in APPLICATION_TABLES:
        raise BackupExportError("Table extérieure au périmètre Quiz Formation.")
    return ('public.' if mode == "postgres" else '') + '"' + table + '"'


@contextmanager
def _snapshot(mode: str, sqlite_path: Optional[Path]) -> Iterator[Any]:
    if mode == "sqlite":
        path = Path(sqlite_path if sqlite_path is not None else get_sqlite_path()).resolve()
        if not path.is_file():
            raise BackupExportError(
                "La base SQLite n'existe pas. Ouvre d'abord l'application avec sa base habituelle."
            )
        conn = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA query_only = ON")
            conn.execute("BEGIN")
            yield conn
        finally:
            conn.rollback()
            conn.close()
    elif mode == "postgres":
        with get_postgres_connection() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
                yield conn
    else:
        raise BackupExportError("Le moteur de base de données n'est pas pris en charge.")


def _tables(conn: Any, mode: str) -> List[str]:
    if mode == "sqlite":
        return [
            row["name"] for row in conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
        ]
    with conn.cursor() as cur:
        cur.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' ORDER BY table_name"
        )
        return [row["table_name"] for row in cur.fetchall()]


def _columns(conn: Any, mode: str, table: str) -> List[Dict[str, Any]]:
    if mode == "sqlite":
        return [
            {
                "name": row["name"], "data_type": row["type"],
                "nullable": not bool(row["notnull"]), "default": row["dflt_value"],
                "primary_key_position": row["pk"],
            }
            for row in conn.execute("PRAGMA table_info(" + _safe_table(table, mode) + ")")
        ]
    with conn.cursor() as cur:
        cur.execute(
            "SELECT column_name, data_type, is_nullable, column_default, udt_name "
            "FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = %s ORDER BY ordinal_position",
            (table,),
        )
        return [
            {
                "name": row["column_name"], "data_type": row["data_type"],
                "nullable": row["is_nullable"] == "YES", "default": row["column_default"],
                "native_type": row["udt_name"],
            }
            for row in cur.fetchall()
        ]


@contextmanager
def _rows(conn: Any, mode: str, table: str, columns: List[Dict[str, Any]]) -> Iterator[Any]:
    projection = "*"
    if mode == "postgres":
        expressions = []
        for column in columns:
            name = '"' + column["name"].replace('"', '""') + '"'
            # A JSONB number can exceed Python float precision. Cast on the
            # server before psycopg's JSON loader has a chance to round it.
            if column["data_type"] in {"json", "jsonb"}:
                expressions.append(name + "::text AS " + name)
            else:
                expressions.append(name)
        projection = ", ".join(expressions)
    sql = "SELECT " + projection + " FROM " + _safe_table(table, mode)
    if any(column["name"] == "id" for column in columns):
        sql += ' ORDER BY "id"'
    if mode == "sqlite":
        cursor = conn.execute(sql)
        try:
            yield cursor
        finally:
            cursor.close()
    else:
        # A server-side cursor keeps large exports bounded in memory.
        with conn.cursor(name="quiz_formation_backup_" + table) as cursor:
            cursor.execute(sql)
            yield cursor


def _media_sources(value: Any) -> Iterator[str]:
    """Recognize the forms accepted by render_question_media, including contexts."""
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"image_url", "media_url"} and isinstance(child, str) and child.strip():
                yield child.strip()
            if key == "media":
                entries = child if isinstance(child, list) else [child]
                for entry in entries:
                    if isinstance(entry, str) and entry.strip():
                        yield entry.strip()
                    elif isinstance(entry, dict):
                        source = next((entry.get(k) for k in ("url", "path", "source", "src") if entry.get(k)), None)
                        if isinstance(source, str) and source.strip():
                            yield source.strip()
            if isinstance(child, (dict, list)):
                yield from _media_sources(child)
    elif isinstance(value, list):
        for child in value:
            yield from _media_sources(child)


def _record_media(row: Dict[str, Any], references: Dict[str, Dict[str, Any]]) -> None:
    for key, value in row.items():
        if not key.endswith("_json"):
            continue
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except (TypeError, ValueError):
                continue  # Invalid JSON is still exported unchanged as source evidence.
        for source in _media_sources(value):
            digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
            if digest not in references:
                references[digest] = {"source": source, "occurrences": 0}
            references[digest]["occurrences"] += 1


def _write_table(archive: zipfile.ZipFile, budget: _Budget, conn: Any, mode: str,
                 table: str, references: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    if mode == "postgres":
        with conn.cursor() as cur:
            cur.execute(
                "SELECT row_security_active(%s::regclass) AS active, "
                "has_table_privilege(%s, 'SELECT') AS all_columns_readable",
                ("public." + table, "public." + table),
            )
            permission = cur.fetchone()
            if permission["active"]:
                raise BackupExportError(
                    "Les règles de sécurité PostgreSQL peuvent masquer des lignes de " + table + ". "
                    "Utilise la connexion de sauvegarde autorisée. Aucune archive partielle n'a été produite."
                )
            if not permission["all_columns_readable"]:
                raise BackupExportError(
                    "La connexion ne permet pas de lire toutes les colonnes de " + table + ". "
                    "Aucune archive partielle n'a été produite."
                )
    columns = _columns(conn, mode, table)
    if not columns:
        raise BackupExportError("Le schéma de la table " + table + " n'est pas accessible.")
    filename = "tables/" + table + ".json"
    digest = hashlib.sha256()
    count = 0
    with archive.open(filename, "w") as output:
        def write(chunk: bytes) -> None:
            budget.consume(len(chunk))
            output.write(chunk)
            digest.update(chunk)
        header = _json_bytes({"table": table, "columns": columns})
        write(header[:-1] + b',"rows":[\n')
        with _rows(conn, mode, table, columns) as cursor:
            while True:
                # Uploaded media can make one row several megabytes large.
                batch = cursor.fetchmany(25)
                if not batch:
                    break
                for raw_row in batch:
                    row = dict(raw_row)
                    if count:
                        write(b",\n")
                    write(_json_bytes(row))
                    _record_media(row, references)
                    count += 1
        write(b"\n]}\n")
    return {"name": table, "path": filename, "row_count": count, "sha256": digest.hexdigest()}


def _local_media_path(source: str, project_root: Path) -> Tuple[Optional[Path], str]:
    parsed = urlsplit(source)
    if parsed.scheme or parsed.netloc or source.startswith(("\\", "//")):
        return None, "unsupported_scheme"
    # A URL path may be encoded. Query fragments are not filesystem names.
    raw_path = unquote(parsed.path)
    if "\\" in raw_path or "\x00" in raw_path:
        return None, "outside_media_directories"
    candidate = Path(raw_path)
    if candidate.is_absolute():
        candidate = candidate.resolve()
    else:
        candidate = (project_root / candidate).resolve()
    allowed_roots = [project_root / directory for directory in MEDIA_DIRECTORIES]
    if not any(candidate.is_relative_to(root) for root in allowed_roots):
        return None, "outside_media_directories"
    relative = candidate.relative_to(project_root)
    if any(part.startswith(".") for part in relative.parts):
        return None, "outside_media_directories"
    if candidate.suffix.lower() not in MEDIA_EXTENSIONS:
        return None, "unsupported_extension"
    if candidate.name.lower().startswith(("secrets.", ".env", "credentials.")):
        return None, "excluded_configuration"
    if not candidate.is_file():
        return None, "missing"
    return candidate, "included"


def _write_media(archive: zipfile.ZipFile, budget: _Budget, references: Dict[str, Dict[str, Any]],
                 project_root: Path) -> Dict[str, Any]:
    records: List[Dict[str, Any]] = []
    packed: Dict[Path, Dict[str, Any]] = {}
    for source_hash, reference in sorted(references.items()):
        source = reference["source"]
        record: Dict[str, Any] = {"reference_sha256": source_hash, "occurrences": reference["occurrences"]}
        if source.lower().startswith("data:"):
            record["status"] = "embedded_in_json"
            records.append(record)
            continue
        record["source"] = source
        try:
            parsed = urlsplit(source)
        except ValueError:
            record["status"] = "invalid_reference"
            records.append(record)
            continue
        if parsed.scheme.lower() in {"http", "https"} or parsed.netloc:
            record["status"] = "external_not_downloaded"
            records.append(record)
            continue
        path, status = _local_media_path(source, project_root)
        record["status"] = status
        if path is not None:
            if path not in packed:
                archive_path = "media/" + path.relative_to(project_root).as_posix()
                digest = hashlib.sha256()
                byte_count = 0
                try:
                    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
                    with os.fdopen(descriptor, "rb") as input_file:
                        before = os.fstat(input_file.fileno())
                        if not stat.S_ISREG(before.st_mode):
                            raise BackupExportError("Un média local n'est pas un fichier régulier.")
                        with archive.open(archive_path, "w") as output:
                            while True:
                                chunk = input_file.read(64 * 1024)
                                if not chunk:
                                    break
                                budget.consume(len(chunk))
                                output.write(chunk)
                                digest.update(chunk)
                                byte_count += len(chunk)
                        after = os.fstat(input_file.fileno())
                        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                            raise BackupExportError(
                                "Un média a changé pendant la sauvegarde. Relance l'export. "
                                "Aucune archive partielle n'a été produite."
                            )
                except OSError as exc:
                    # A failed read can leave a partial ZIP member: abort the whole package.
                    raise BackupExportError(
                        "Un média local ne peut pas être lu. Aucune archive partielle n'a été produite."
                    ) from exc
                packed[path] = {"path": archive_path, "size_bytes": byte_count, "sha256": digest.hexdigest()}
            record.update(packed[path])
        records.append(record)
    unresolved = [record for record in records if record["status"] not in {"embedded_in_json", "included"}]
    return {
        "references": records,
        "embedded_count": sum(r["status"] == "embedded_in_json" for r in records),
        "packed_count": len(packed),
        "external_count": sum(r["status"] == "external_not_downloaded" for r in records),
        "unresolved_count": len(unresolved),
        "all_referenced_media_included": not unresolved,
    }


_README = """QUIZ FORMATION - EXPORT PORTABLE

manifest.json décrit le périmètre, le moteur, les nombres de lignes, les médias
et les empreintes SHA-256. Chaque tables/<nom>.json conserve toutes les colonnes
et toutes les lignes visibles dans le même instantané de base de données.
Aucun filtre de formation, d'activité, de date ou de nombre de lignes n'est appliqué.

Les JSON stockés en texte dans SQLite restent des chaînes intactes. Les colonnes
JSON/JSONB PostgreSQL sont exportées en texte JSON produit par le serveur
(canonique pour JSONB), sans conversion intermédiaire de leurs nombres en float.
Le type natif de chaque colonne permet de distinguer ces chaînes du texte métier.
Les valeurs non natives JSON utilisent une
enveloppe {"__quiz_backup_type__": "...", "value": "..."} : decimal, datetime,
date, time, uuid, bytes (base64) ou float non fini. Les types des colonnes figurent
dans chaque fichier. Toute future restauration doit respecter ces types sans
interpréter arbitrairement une clé identique présente dans un JSON métier.

Les images embarquées en data URI restent dans les données. Les médias locaux
référencés et autorisés sont copiés dans media/. Seuls assets/, media/, uploads/,
data/media/ et data/uploads/ sous le projet sont autorisés. Les liens externes
ne sont jamais téléchargés. Le manifeste liste les références non emballées.
Les sources d'origine ne sont pas réécrites.

Ce fichier contient les données personnelles des apprenants, leurs réponses,
les corrigés et les codes d'accès des sessions enregistrées. Conservez-le dans
un emplacement réservé au formateur. Aucun fichier de configuration, mot de
passe formateur, clé API ou chaîne de connexion n'est collecté par cet export.

Cet export porte sur les neuf tables connues de Quiz Formation. Les tables
absentes ou extérieures à ce périmètre sont indiquées dans le manifeste.
Il ne contient pas les brouillons en mémoire non enregistrés, le code du projet,
les réglages d'hébergement, les droits du serveur ni les médias distants.
Il ne constitue pas une sauvegarde native du serveur PostgreSQL. Il n'inclut pas
les séquences d'identifiants, fonctions SQL ou politiques de sécurité du serveur.

Aucune restauration automatique n'est fournie. Le ZIP de sauvegarde ne doit pas
être importé comme un quiz. Conservez l'original avant toute conversion. Vérifiez
les compteurs et les réserves du manifeste avant de considérer le périmètre couvert.
"""


def create_backup_archive(
    *, sqlite_path: Optional[Path] = None, project_root: Optional[Path] = None,
    max_uncompressed_bytes: int = DEFAULT_MAX_UNCOMPRESSED_BYTES,
) -> BackupArchive:
    """Export persisted data without writes, implicit migrations or row limits.

    ``sqlite_path`` is an optional path override for local use and tests; it does
    not switch a configured PostgreSQL backend to SQLite. The caller must enforce
    the trainer's authorization before exposing this function or its bytes.
    """
    budget = _Budget(max_uncompressed_bytes)
    root = Path(project_root if project_root is not None else PROJECT_ROOT).resolve()
    created = datetime.now(timezone.utc)
    output = io.BytesIO()
    try:
        mode = get_database_mode()
        references: Dict[str, Dict[str, Any]] = {}
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            with _snapshot(mode, sqlite_path) as conn:
                found = _tables(conn, mode)
                selected = [table for table in APPLICATION_TABLES if table in found]
                if not selected:
                    raise BackupExportError(
                        "Aucune table Quiz Formation n'est présente dans la base sélectionnée."
                    )
                table_exports = [
                    _write_table(archive, budget, conn, mode, table, references)
                    for table in selected
                ]
            media = _write_media(archive, budget, references, root)
            missing = [table for table in APPLICATION_TABLES if table not in found]
            unrecognized = [table for table in found if table not in APPLICATION_TABLES]
            warnings = []
            required_missing = [table for table in missing if table not in OPTIONAL_TABLES]
            if required_missing:
                warnings.append("Certaines tables applicatives ne sont pas présentes dans cette base.")
            if unrecognized:
                warnings.append("Des tables extérieures au périmètre Quiz Formation ne sont pas exportées.")
            if media["unresolved_count"]:
                warnings.append("Certains médias restent des références et ne sont pas inclus dans l'archive.")
            manifest = {
                "format": "quiz-formation-backup", "format_version": FORMAT_VERSION,
                "created_at_utc": created.isoformat(), "database_engine": mode,
                "snapshot": "read_only_transaction" if mode == "sqlite" else "repeatable_read_read_only",
                "tables": table_exports,
                "row_counts": {table["name"]: table["row_count"] for table in table_exports},
                "total_rows": sum(table["row_count"] for table in table_exports),
                "missing_tables": missing, "unrecognized_tables_not_exported": unrecognized,
                "media": media, "warnings": warnings,
                "all_present_application_tables_exported": True,
                "all_expected_tables_present": not required_missing,
                "restoration_supported": False,
                "contains_personal_data": True,
                "contains_session_access_codes": "training_sessions" in selected,
                "size_limit_uncompressed_bytes": max_uncompressed_bytes,
                "excluded": [
                    "unsaved_session_state", "environment_and_secrets", "remote_media_bytes",
                    "application_source_code", "server_roles_policies_and_sequences",
                ],
            }
            readme = _README.encode("utf-8")
            budget.consume(len(readme))
            archive.writestr("LIRE_MOI.txt", readme)
            manifest_bytes = _json_bytes(manifest)
            budget.consume(len(manifest_bytes))
            archive.writestr("manifest.json", manifest_bytes)
        return BackupArchive(
            data=output.getvalue(),
            filename="quiz_formation_sauvegarde_" + created.strftime("%Y%m%dT%H%M%S_%fZ") + ".zip",
            manifest=manifest,
        )
    except BackupExportError:
        raise
    except Exception as exc:
        raise BackupExportError(
            "La sauvegarde n'a pas pu être créée. Vérifie l'accès à la base et réessaie. "
            "Aucune archive partielle n'a été produite."
        ) from exc
