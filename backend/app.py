import os
from pathlib import Path
from typing import Any, Dict

from flask import Flask, jsonify, render_template, request, send_from_directory
from flask_cors import CORS

try:  # When executed via `python -m backend.app`
    from .media_manager import MediaManager, UnsupportedMediaType
    from .playback import PlaybackController
except ImportError:  # Fallback for direct execution
    from media_manager import MediaManager, UnsupportedMediaType  # type: ignore
    from playback import PlaybackController  # type: ignore

BASE_DIR = Path(__file__).resolve().parent
MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT", BASE_DIR.parent / "media")).resolve()
AUTO_START_LAST = os.environ.get("AUTO_START_LAST", "0").lower() in {"1", "true", "yes"}

app = Flask(
    __name__,
    static_folder=str(BASE_DIR / "static"),
    template_folder=str(BASE_DIR / "templates"),
)
app.config["MAX_CONTENT_LENGTH"] = 512 * 1024 * 1024  # 512 MB uploads
CORS(app)

media_manager = MediaManager(MEDIA_ROOT)
playback = PlaybackController()


def make_error(message: str, status: int = 400):
    response = jsonify({"error": message})
    response.status_code = status
    return response


@app.route("/api/media", methods=["GET"])
def list_media():
    return jsonify({"items": media_manager.list_media()})


@app.route("/api/media", methods=["POST"])
def upload_media():
    if "file" not in request.files:
        return make_error("Missing file upload", 400)
    file = request.files["file"]
    if not file.filename:
        return make_error("Uploaded file has no filename", 400)
    try:
        item = media_manager.add_media(file)
    except UnsupportedMediaType as exc:
        return make_error(str(exc), 415)
    return jsonify(item), 201


@app.route("/api/media/<media_id>", methods=["DELETE"])
def delete_media(media_id: str):
    removed = media_manager.delete_media(media_id)
    if not removed:
        return make_error("Media item not found", 404)
    return ("", 204)


@app.route("/api/media/<media_id>/play", methods=["POST"])
def play_media(media_id: str):
    item = media_manager.get_media(media_id)
    if not item:
        return make_error("Media item not found", 404)
    media_path = MEDIA_ROOT / item["filename"]
    if not media_path.exists():
        return make_error("Media file missing on disk", 410)

    try:
        playback.play(media_path, item["media_type"], item["id"])
    except FileNotFoundError:
        return make_error("mpv executable not found. Install mpv to enable playback.", 500)
    except Exception as exc:  # pragma: no cover - defensive logging
        return make_error(f"Failed to start playback: {exc}", 500)

    media_manager.record_last_played(media_id)

    return jsonify({"status": "playing", "media": item})


@app.route("/api/stop", methods=["POST"])
def stop_media():
    playback.stop()
    return jsonify({"status": "stopped"})


@app.route("/api/status", methods=["GET"])
def playback_status():
    status: Dict[str, Any] = {"status": "idle"}
    current = playback.status()
    if current:
        media = media_manager.get_media(current["media_id"])
        status = {
            "status": "playing",
            "media": media,
            "details": current,
        }
    return jsonify(status)


@app.route("/media/<path:filename>")
def serve_media(filename: str):
    return send_from_directory(MEDIA_ROOT, filename)


@app.route("/")
def index():
    return render_template("index.html")


def _auto_start_last() -> None:
    last = media_manager.last_played()
    if not last:
        return
    media_path = MEDIA_ROOT / last["filename"]
    if not media_path.exists():
        return
    try:
        playback.play(media_path, last["media_type"], last["id"])
    except FileNotFoundError:
        print("mpv executable not found. Skipping auto-start.")
    except Exception as exc:
        print(f"Failed to auto-start last media: {exc}")


if AUTO_START_LAST:
    _auto_start_last()


if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    app.run(host=host, port=port)
