from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Iterable

from flask import current_app

from . import db


def allowed_file(filename: str) -> tuple[bool, str | None]:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    images = current_app.config["ALLOWED_IMAGE_EXTENSIONS"]
    videos = current_app.config["ALLOWED_VIDEO_EXTENSIONS"]
    if ext in images:
        return True, "image"
    if ext in videos:
        return True, "video"
    return False, None


def save_media_file(storage) -> dict[str, Any]:
    filename = storage.filename or ""
    is_allowed, media_type = allowed_file(filename)
    if not is_allowed or media_type is None:
        raise ValueError("Unsupported file type")

    ext = filename.rsplit(".", 1)[-1].lower()
    safe_name = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}.{ext}"
    media_root = current_app.config["MEDIA_ROOT"]
    storage.save(os.path.join(media_root, safe_name))

    conn = db.get_db()
    conn.execute(
        "INSERT INTO media(filename, original_name, media_type, duration_default, uploaded_at)\n         VALUES (?, ?, ?, ?, ?)",
        (safe_name, filename, media_type, default_duration(media_type), datetime.utcnow().isoformat()),
    )
    media_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    return get_media(media_id)


def default_duration(media_type: str) -> int | None:
    if media_type == "image":
        return 8
    return None


def get_media(media_id: int) -> dict[str, Any] | None:
    row = db.query("SELECT * FROM media WHERE id = ?", (media_id,), one=True)
    if row:
        return dict(row)
    return None


def list_media() -> list[dict[str, Any]]:
    rows = db.query("SELECT * FROM media ORDER BY uploaded_at DESC")
    return [dict(r) for r in rows]


def delete_media(media_id: int) -> None:
    record = db.query("SELECT filename FROM media WHERE id = ?", (media_id,), one=True)
    if not record:
        return
    db.execute("DELETE FROM media WHERE id = ?", (media_id,))
    file_path = os.path.join(current_app.config["MEDIA_ROOT"], record["filename"])
    try:
        os.remove(file_path)
    except FileNotFoundError:
        pass


def set_active_playlist(items: Iterable[dict[str, Any]]) -> dict[str, Any]:
    conn = db.get_db()
    conn.execute("DELETE FROM active_playlist")
    for position, item in enumerate(items):
        conn.execute(
            "INSERT INTO active_playlist(media_id, position, duration) VALUES (?, ?, ?)",
            (item["media_id"], position, item.get("duration")),
        )
    version = datetime.utcnow().isoformat()
    db.set_meta("playlist_version", version)
    return {
        "version": version,
        "items": get_active_playlist()["items"],
    }


def get_active_playlist() -> dict[str, Any]:
    rows = db.query(
        """
        SELECT ap.id,
               ap.media_id,
               ap.position,
               ap.duration,
               m.filename,
               m.media_type,
               m.original_name,
               m.duration_default
        FROM active_playlist ap
        JOIN media m ON m.id = ap.media_id
        ORDER BY ap.position ASC
        """
    )
    version = db.get_meta("playlist_version", datetime.utcnow().isoformat()) or ""
    return {
        "version": version,
        "items": [
            {
                "playlist_item_id": row["id"],
                "media_id": row["media_id"],
                "position": row["position"],
                "duration": row["duration"],
                "filename": row["filename"],
                "media_type": row["media_type"],
                "original_name": row["original_name"],
                "default_duration": row["duration_default"],
            }
            for row in rows
        ],
    }
