from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SQLITE_PATH = PROJECT_ROOT / "data" / "quiz_history.db"


def _streamlit_secret(name: str, default: Optional[str] = None) -> Optional[str]:
    try:
        import streamlit as st  # type: ignore
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:
        pass
    return default


def get_setting(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.environ.get(name)
    if value is not None and str(value).strip() != "":
        return str(value)
    return _streamlit_secret(name, default)


def get_database_mode() -> str:
    mode = (get_setting("APP_DATABASE_MODE", "sqlite") or "sqlite").strip().lower()
    if mode not in {"sqlite", "postgres"}:
        raise ValueError("APP_DATABASE_MODE doit valoir 'sqlite' ou 'postgres'.")
    return mode


def get_sqlite_path() -> Path:
    configured = get_setting("SQLITE_DB_PATH", "data/quiz_history.db") or "data/quiz_history.db"
    path = Path(configured)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def get_database_url() -> str:
    return get_setting("DATABASE_URL", "") or ""


def get_sqlite_connection() -> sqlite3.Connection:
    path = get_sqlite_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def get_postgres_connection():
    database_url = get_database_url()
    if not database_url:
        raise RuntimeError("DATABASE_URL est vide. Renseigne la chaîne de connexion Supabase/PostgreSQL.")
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:
        raise RuntimeError("psycopg n'est pas installé. Lance : pip install -r requirements.txt") from exc
    return psycopg.connect(database_url, row_factory=dict_row)


def get_connection():
    if get_database_mode() == "sqlite":
        return get_sqlite_connection()
    return get_postgres_connection()


def test_connection() -> Dict[str, Any]:
    mode = get_database_mode()
    if mode == "sqlite":
        path = get_sqlite_path()
        with get_sqlite_connection() as conn:
            row = conn.execute("SELECT sqlite_version() AS version").fetchone()
            tables = conn.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type='table'
                ORDER BY name
                """
            ).fetchall()
        return {
            "mode": "sqlite",
            "ok": True,
            "path": str(path),
            "version": row["version"] if row else "",
            "tables": [table["name"] for table in tables],
        }

    with get_postgres_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("select current_database() as database_name, version() as version")
            row = cur.fetchone()
            cur.execute(
                """
                select table_name
                from information_schema.tables
                where table_schema = 'public'
                order by table_name
                """
            )
            tables = cur.fetchall()
    return {
        "mode": "postgres",
        "ok": True,
        "database": row["database_name"] if row else "",
        "version": row["version"] if row else "",
        "tables": [table["table_name"] for table in tables],
    }
