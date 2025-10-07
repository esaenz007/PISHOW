import atexit
import base64
import binascii
import io
import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from flask import Flask, jsonify, render_template, request, send_from_directory
from flask_cors import CORS
from werkzeug.datastructures import FileStorage

try:  # When executed via `python -m backend.app`
    from .media_manager import MediaManager, UnsupportedMediaType
    from .playback import PlaybackController
    from .projector import (
        CECController,
        ProjectorScheduleStore,
        ProjectorScheduler,
        ScheduleValidationError,
    )
except ImportError:  # Fallback for direct execution
    from media_manager import MediaManager, UnsupportedMediaType  # type: ignore
    from playback import PlaybackController  # type: ignore
    from projector import (  # type: ignore
        CECController,
        ProjectorScheduleStore,
        ProjectorScheduler,
        ScheduleValidationError,
    )

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
schedule_store = ProjectorScheduleStore(MEDIA_ROOT)
cec_controller = CECController()
projector_scheduler = ProjectorScheduler(cec_controller, schedule_store)
atexit.register(projector_scheduler.shutdown)


def make_error(message: str, status: int = 400):
    response = jsonify({"error": message})
    response.status_code = status
    return response


def _file_from_json_payload(payload: Dict[str, Any]) -> Tuple[Optional[FileStorage], Optional[str]]:
    if not isinstance(payload, dict):
        return None, "JSON body must be an object"

    content = payload.get("content")
    if not isinstance(content, str) or not content:
        return None, "Missing base64-encoded 'content' field"

    filename = payload.get("filename") or payload.get("name")
    if not isinstance(filename, str) or not filename:
        return None, "Missing 'filename' field"

    try:
        decoded = base64.b64decode(content, validate=True)
    except (ValueError, binascii.Error):
        return None, "Invalid base64 data in 'content'"

    stream = io.BytesIO(decoded)
    file_storage = FileStorage(stream=stream, filename=filename, content_type=payload.get("content_type"))
    stream.seek(0)
    return file_storage, None


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


@app.route("/api/media/upload-and-play", methods=["POST"])
def upload_and_play():
    json_payload = request.get_json(silent=True)
    file: Optional[FileStorage]
    cleanup_stream = False

    if request.is_json and json_payload is None:
        return make_error("Invalid JSON payload", 400)

    if json_payload:
        built_file, error = _file_from_json_payload(json_payload)
        if error:
            return make_error(error, 400)
        file = built_file
        cleanup_stream = True
    else:
        if "file" not in request.files:
            return make_error("Missing file upload", 400)
        file = request.files["file"]

    if file is None or not file.filename:
        if cleanup_stream and file is not None and hasattr(file.stream, "close"):
            file.stream.close()
        return make_error("Uploaded file has no filename", 400)

    item: Optional[Dict[str, Any]] = None
    error_response = None
    try:
        item = media_manager.add_media(file)
    except UnsupportedMediaType as exc:
        error_response = make_error(str(exc), 415)
    finally:
        if cleanup_stream and hasattr(file.stream, "close"):
            file.stream.close()

    if error_response:
        return error_response

    if item is None:
        return make_error("Failed to persist uploaded media", 500)

    media_path = MEDIA_ROOT / item["filename"]
    if not media_path.exists():
        return make_error("Media file missing on disk", 410)

    try:
        playback.play(media_path, item["media_type"], item["id"])
    except FileNotFoundError:
        return make_error("mpv executable not found. Install mpv to enable playback.", 500)
    except Exception as exc:  # pragma: no cover - defensive logging
        return make_error(f"Failed to start playback: {exc}", 500)

    media_manager.record_last_played(item["id"])

    return jsonify({"status": "playing", "media": item}), 201


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


@app.route("/api/projector/power", methods=["POST"])
def projector_power():
    payload = request.get_json(silent=True) or {}
    state = payload.get("state")
    if state not in {"on", "off"}:
        return make_error("Invalid 'state'. Expected 'on' or 'off'.", 400)

    if state == "on":
        success = cec_controller.power_on()
    else:
        success = cec_controller.power_off()

    if not success:
        return make_error("Failed to control the projector via CEC.", 500)

    return jsonify({"status": "ok", "state": state})


@app.route("/api/projector/schedule", methods=["GET"])
def get_projector_schedule():
    return jsonify(schedule_store.read())


@app.route("/api/projector/schedule", methods=["PUT"])
def update_projector_schedule():
    payload = request.get_json(silent=True)
    if payload is None:
        return make_error("Request body must be valid JSON.", 400)
    try:
        schedule = schedule_store.update(payload)
    except ScheduleValidationError as exc:
        return make_error(str(exc), 400)
    projector_scheduler.notify_update()
    return jsonify(schedule)


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
