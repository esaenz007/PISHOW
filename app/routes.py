from __future__ import annotations

from typing import Any

from flask import (
    Blueprint,
    Response,
    current_app,
    jsonify,
    render_template,
    request,
    send_from_directory,
)

from . import db as database
from . import services

bp = Blueprint("main", __name__)


@bp.route("/")
def index() -> str:
    media_items = services.list_media()
    playlist = services.get_active_playlist()
    return render_template(
        "admin.html",
        media_items=media_items,
        playlist=playlist,
        max_upload_mb=current_app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024),
    )


@bp.route("/display")
def display() -> str:
    playlist = services.get_active_playlist()
    return render_template("display.html", playlist=playlist)


@bp.route("/media/<path:filename>")
def media_file(filename: str) -> Response:
    return send_from_directory(current_app.config["MEDIA_ROOT"], filename)


@bp.route("/api/media", methods=["GET"])
def api_list_media() -> Response:
    return jsonify({"media": services.list_media()})


@bp.route("/api/media", methods=["POST"])
def api_upload_media() -> Response:
    if "file" not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400
    try:
        media = services.save_media_file(file)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"media": media}), 201


@bp.route("/api/media/<int:media_id>", methods=["DELETE"])
def api_delete_media(media_id: int) -> Response:
    services.delete_media(media_id)
    return jsonify({"status": "ok"})


@bp.route("/api/media/<int:media_id>/duration", methods=["POST"])
def api_set_media_duration(media_id: int) -> Response:
    data: dict[str, Any] = request.get_json(silent=True) or {}
    duration = data.get("duration")
    if duration is not None and (not isinstance(duration, (int, float)) or duration <= 0):
        return jsonify({"error": "Duration must be a positive number"}), 400
    conn = database.get_db()
    conn.execute(
        "UPDATE media SET duration_default = ? WHERE id = ?",
        (int(duration) if duration is not None else None, media_id),
    )
    return jsonify({"status": "ok"})


@bp.route("/api/playlist", methods=["GET"])
def api_get_playlist() -> Response:
    playlist = services.get_active_playlist()
    return jsonify(playlist)


@bp.route("/api/playlist", methods=["POST"])
def api_set_playlist() -> Response:
    payload = request.get_json(silent=True)
    if not payload or "items" not in payload:
        return jsonify({"error": "Missing items"}), 400
    try:
        normalized_items = _normalize_playlist_items(payload["items"])
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    playlist = services.set_active_playlist(normalized_items)
    return jsonify(playlist)


@bp.route("/api/playlist", methods=["DELETE"])
def api_clear_playlist() -> Response:
    services.set_active_playlist([])
    return jsonify({"status": "ok"})


def _normalize_playlist_items(items: list[Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"Item at position {index} is invalid")
        media_id = item.get("media_id")
        if not isinstance(media_id, int):
            raise ValueError("media_id must be an integer")
        duration = item.get("duration")
        if duration is not None:
            if not isinstance(duration, (int, float)):
                raise ValueError("duration must be numeric")
            duration = int(duration)
            if duration <= 0:
                raise ValueError("duration must be positive")
        normalized.append({"media_id": media_id, "duration": duration})
    return normalized


def init_app(app) -> None:
    app.register_blueprint(bp)
