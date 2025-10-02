from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any, Iterable, Sequence

import click
from flask import current_app, g


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(
            current_app.config["DATABASE"],
            detect_types=sqlite3.PARSE_DECLTYPES,
            isolation_level=None,
        )
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(_: Exception | None = None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    db = get_db()
    db.executescript(
        """
        PRAGMA foreign_keys = ON;

        CREATE TABLE IF NOT EXISTS media (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL UNIQUE,
            original_name TEXT NOT NULL,
            media_type TEXT NOT NULL CHECK (media_type IN ('image', 'video')),
            duration_default INTEGER,
            uploaded_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS active_playlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            media_id INTEGER NOT NULL REFERENCES media(id) ON DELETE CASCADE,
            position INTEGER NOT NULL,
            duration INTEGER,
            UNIQUE(position)
        );

        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """
    )
    ensure_meta("playlist_version", datetime.utcnow().isoformat())


def ensure_meta(key: str, default: str) -> None:
    db = get_db()
    existing = db.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    if existing is None:
        db.execute("INSERT INTO meta(key, value) VALUES (?, ?)", (key, default))


def set_meta(key: str, value: str) -> None:
    db = get_db()
    db.execute(
        "INSERT INTO meta(key, value) VALUES (?, ?)\n         ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def get_meta(key: str, default: str | None = None) -> str | None:
    db = get_db()
    row = db.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    if row:
        return row["value"]
    return default


def query(
    sql: str,
    args: Sequence[Any] | None = None,
    *,
    one: bool = False,
):
    db = get_db()
    cur = db.execute(sql, args or [])
    rv = cur.fetchall()
    cur.close()
    return (rv[0] if rv else None) if one else rv


def execute(sql: str, args: Iterable[Any] | None = None) -> None:
    db = get_db()
    db.execute(sql, args or [])


def init_app(app) -> None:
    @app.teardown_appcontext
    def teardown(_: Exception | None) -> None:  # pragma: no cover - Flask hook
        close_db()

    @app.cli.command("init-db")
    def init_db_command() -> None:  # pragma: no cover - CLI command
        init_db()
        click.echo("Initialized the database.")
