import json
import logging
import os
import subprocess
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional, Tuple

TIME_FORMAT = "%H:%M"

DEFAULT_SCHEDULE: Dict[str, Dict[str, Optional[str]]] = {
    "power_on": {"enabled": False, "time": None},
    "power_off": {"enabled": False, "time": None},
}


class ScheduleValidationError(ValueError):
    """Raised when a projector schedule payload is invalid."""


class ProjectorScheduleStore:
    """Persistence helper for projector on/off schedule."""

    def __init__(self, media_root: Path):
        self._file = media_root / "projector_schedule.json"
        self._lock = threading.Lock()
        if not self._file.exists():
            self._write(DEFAULT_SCHEDULE)

    def read(self) -> Dict[str, Dict[str, Optional[str]]]:
        with self._lock:
            with self._file.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        return {
            "power_on": {
                "enabled": bool(data.get("power_on", {}).get("enabled")),
                "time": data.get("power_on", {}).get("time"),
            },
            "power_off": {
                "enabled": bool(data.get("power_off", {}).get("enabled")),
                "time": data.get("power_off", {}).get("time"),
            },
        }

    def update(self, payload: Dict) -> Dict[str, Dict[str, Optional[str]]]:
        schedule = {
            "power_on": self._normalize_entry(payload.get("power_on"), "power_on"),
            "power_off": self._normalize_entry(payload.get("power_off"), "power_off"),
        }
        with self._lock:
            self._write(schedule)
        return schedule

    def _normalize_entry(self, entry: Optional[Dict], label: str) -> Dict[str, Optional[str]]:
        entry = entry or {}
        enabled = bool(entry.get("enabled"))
        time_value = entry.get("time")
        if time_value in ("", None):
            time_value = None
        elif isinstance(time_value, str):
            time_value = time_value.strip()
            if not time_value:
                time_value = None
            else:
                try:
                    datetime.strptime(time_value, TIME_FORMAT)
                except ValueError as exc:
                    raise ScheduleValidationError(
                        f"{label}.time must use HH:MM (24-hour) format"
                    ) from exc
        else:
            raise ScheduleValidationError(f"{label}.time must be a string or null")
        return {"enabled": enabled, "time": time_value}

    def _write(self, schedule: Dict[str, Dict[str, Optional[str]]]) -> None:
        with self._file.open("w", encoding="utf-8") as handle:
            json.dump(schedule, handle, indent=2)
            handle.write("\n")


class CECController:
    """Wrapper around common CEC utilities to power the projector."""

    def __init__(
        self,
        tool: Optional[str] = None,
        device: Optional[str] = None,
        logical_address: Optional[str] = None,
    ) -> None:
        self._tool = tool or os.environ.get("PROJECTOR_CEC_TOOL", "cec-ctl")
        self._device = device or os.environ.get("PROJECTOR_CEC_DEVICE")
        self._logical_address = logical_address or os.environ.get("PROJECTOR_CEC_LOGICAL_ADDR", "0")

    def power_on(self) -> bool:
        return self._run_cec_command(["--power", "on"])

    def power_off(self) -> bool:
        return self._run_cec_command(["--standby"])

    def _run_cec_command(self, args: list) -> bool:
        if not self._tool:
            logging.error("CEC tool is not configured; skipping projector command.")
            return False

        command = [self._tool]
        if self._device:
            command.extend(["--device", self._device])
        if self._logical_address:
            command.extend(["--to", str(self._logical_address)])
        command.extend(args)

        try:
            subprocess.run(
                command,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            logging.info("Sent CEC command: %s", " ".join(command))
            return True
        except FileNotFoundError:
            logging.error("CEC tool '%s' not found. Install cec-ctl or configure PROJECTOR_CEC_TOOL.", self._tool)
        except subprocess.CalledProcessError as exc:
            logging.error("CEC command failed with exit code %s: %s", exc.returncode, " ".join(command))
        return False


class ProjectorScheduler:
    """Background scheduler that powers the projector on/off at configured times."""

    def __init__(self, cec_controller: CECController, schedule_store: ProjectorScheduleStore) -> None:
        self._cec = cec_controller
        self._schedule_store = schedule_store
        self._wake_event = threading.Event()
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, name="ProjectorScheduler", daemon=True)
        self._thread.start()

    def notify_update(self) -> None:
        self._wake_event.set()

    def shutdown(self) -> None:
        self._stop_event.set()
        self._wake_event.set()
        self._thread.join(timeout=5)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            next_event = self._next_event()
            if not next_event:
                self._wait_with_wake(3600)
                continue

            run_at, action = next_event
            now = datetime.now()
            delay = (run_at - now).total_seconds()
            if delay <= 0:
                self._execute(action)
                continue

            woke_early = self._wait_with_wake(delay)
            if woke_early:
                continue
            self._execute(action)

    def _wait_with_wake(self, timeout: float) -> bool:
        try:
            woke_early = self._wake_event.wait(timeout=timeout)
        finally:
            self._wake_event.clear()
        return woke_early

    def _next_event(self) -> Optional[Tuple[datetime, str]]:
        schedule = self._schedule_store.read()
        now = datetime.now()
        events = []

        for action in ("power_on", "power_off"):
            entry = schedule.get(action) or {}
            if not entry.get("enabled"):
                continue
            time_str = entry.get("time")
            if not time_str:
                continue
            try:
                target_time = datetime.strptime(time_str, TIME_FORMAT).time()
            except ValueError:
                logging.warning("Skipping invalid time '%s' for %s", time_str, action)
                continue
            candidate = now.replace(
                hour=target_time.hour,
                minute=target_time.minute,
                second=0,
                microsecond=0,
            )
            if candidate <= now:
                candidate += timedelta(days=1)
            events.append((candidate, action))

        if not events:
            return None

        events.sort(key=lambda item: item[0])
        return events[0]

    def _execute(self, action: str) -> None:
        schedule = self._schedule_store.read()
        entry = schedule.get(action) or {}
        if not entry.get("enabled"):
            return  # Schedule disabled before execution window.

        if action == "power_on":
            succeeded = self._cec.power_on()
        elif action == "power_off":
            succeeded = self._cec.power_off()
        else:
            logging.warning("Unknown projector action '%s'.", action)
            return

        if succeeded:
            logging.info("Projector %s action executed successfully.", action.replace("_", " "))
        else:
            logging.error("Projector %s action failed to execute.", action.replace("_", " "))
