import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from werkzeug.datastructures import FileStorage

IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".bmp",
    ".webp",
}

VIDEO_EXTENSIONS = {
    ".mp4",
    ".mkv",
    ".mov",
    ".avi",
    ".webm",
    ".m4v",
}

GALLERY_DEFAULT = {
    "items": [],
    "last_played_id": None,
    "last_played_at": None,
}


class UnsupportedMediaType(Exception):
    """Raised when a file does not match supported image or video types."""


class MediaManager:
    def __init__(self, media_root: Path):
        self.media_root = media_root
        self.media_root.mkdir(parents=True, exist_ok=True)
        self._gallery_file = self.media_root / "gallery.json"
        self._lock = threading.Lock()
        if not self._gallery_file.exists():
            self._write_gallery(GALLERY_DEFAULT)

    def list_media(self) -> List[Dict]:
        gallery = self._read_gallery()
        return list(sorted(gallery["items"], key=lambda item: item["created_at"], reverse=True))

    def get_media(self, media_id: str) -> Optional[Dict]:
        gallery = self._read_gallery()
        return next((item for item in gallery["items"] if item["id"] == media_id), None)

    def add_media(self, file: FileStorage) -> Dict:
        extension = Path(file.filename or "").suffix.lower()
        if extension in IMAGE_EXTENSIONS:
            media_type = "image"
        elif extension in VIDEO_EXTENSIONS:
            media_type = "video"
        else:
            raise UnsupportedMediaType(f"Extension '{extension}' is not supported")

        media_id = uuid.uuid4().hex
        safe_name = f"{media_id}{extension}"
        destination = self.media_root / safe_name
        file.save(destination)

        item = {
            "id": media_id,
            "filename": safe_name,
            "original_name": file.filename,
            "media_type": media_type,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        with self._lock:
            gallery = self._read_gallery()
            gallery["items"].append(item)
            self._write_gallery(gallery)

        return item

    def delete_media(self, media_id: str) -> bool:
        filename = None
        with self._lock:
            gallery = self._read_gallery()
            remaining = []
            for item in gallery["items"]:
                if item["id"] == media_id:
                    filename = item["filename"]
                    continue
                remaining.append(item)

            if filename is None:
                return False

            gallery["items"] = remaining
            if gallery.get("last_played_id") == media_id:
                gallery["last_played_id"] = None
                gallery["last_played_at"] = None
            self._write_gallery(gallery)

        if filename:
            media_file = self.media_root / filename
            if media_file.exists():
                media_file.unlink()
        return True

    def record_last_played(self, media_id: str) -> None:
        with self._lock:
            gallery = self._read_gallery()
            gallery["last_played_id"] = media_id
            gallery["last_played_at"] = datetime.now(timezone.utc).isoformat()
            self._write_gallery(gallery)

    def last_played(self) -> Optional[Dict]:
        gallery = self._read_gallery()
        media_id = gallery.get("last_played_id")
        if not media_id:
            return None
        return self.get_media(media_id)

    def _read_gallery(self) -> Dict:
        with self._gallery_file.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _write_gallery(self, gallery: Dict) -> None:
        with self._gallery_file.open("w", encoding="utf-8") as handle:
            json.dump(gallery, handle, indent=2)
            handle.write("\n")
