import os
import subprocess
import threading
from pathlib import Path
from typing import Optional


class PlaybackController:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._process: Optional[subprocess.Popen] = None
        self._current: Optional[dict] = None
        extra_args = os.environ.get("MPV_EXTRA_ARGS", "")
        self._extra_args = [arg for arg in extra_args.split() if arg]

    def play(self, media_path: Path, media_type: str, media_id: str) -> None:
        media_path = media_path.resolve()
        command = self._build_command(media_path, media_type)

        with self._lock:
            self._stop_locked()
            process = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._process = process
            self._current = {
                "media_id": media_id,
                "media_type": media_type,
                "path": str(media_path),
                "command": command,
            }

    def stop(self) -> None:
        with self._lock:
            self._stop_locked()
            self._current = None

    def status(self) -> Optional[dict]:
        with self._lock:
            if self._process and self._process.poll() is not None:
                self._process = None
                self._current = None
            return self._current

    def _stop_locked(self) -> None:
        if self._process and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=5)
        self._process = None

    def _build_command(self, media_path: Path, media_type: str) -> list:
        command = [
            "mpv",
            "--fs",
            "--no-terminal",
            *self._extra_args,
        ]
        if media_type == "video":
            command.extend(["--loop=inf", str(media_path)])
        else:
            command.extend([
                "--loop-file=inf",
                "--image-display-duration=inf",
                "--keep-open=yes",
                str(media_path),
            ])
        return command
