# PISHOW

Simple Flask-based controller for projecting images and looping videos on a Raspberry Pi 5. The app exposes a web UI to upload media, manage a gallery, and trigger playback on a projector connected to HDMI0.

## Features

- Drag-and-drop style gallery with inline previews of images and videos.
- Upload management supporting common image formats (JPG/PNG/GIF/WebP) and video formats (MP4/MKV/MOV/AVI/WEBM).
- One-click playback control that launches media in `mpv` fullscreen on the Pi's projector output.
- Video playback loops seamlessly until you stop it or pick a different item.
- Image playback stays on-screen indefinitely with no fade-out between switches.
- Automated projector power schedule that sends HDMI-CEC on/off commands at configured times.
- Remembers the last item that played and can automatically resume it on boot.

## Requirements

- Raspberry Pi OS (64-bit Lite) on a Raspberry Pi 5.
- Projector connected to HDMI 0.
- Python 3.11+
- `mpv` media player (`sudo apt install mpv`).
- Optional: set `MPV_EXTRA_ARGS` to pass extra flags such as `--gpu-context=drm` if you are running without X/Wayland.

## Setup

```bash
# Clone the repository (adjust path as needed)
git clone https://example.com/PISHOW.git
cd PISHOW

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

If you prefer not to use a virtual environment, install the packages system-wide with `sudo pip3 install -r requirements.txt`.

## Running the web app

```bash
# From the project root (inside the venv if you created one)
python3 -m backend.app
```

By default the server listens on `0.0.0.0:8000`. Visit `http://<pi-address>:8000/` from another device on the network to access the controller UI.

Environment variables:

- `HOST` (default `0.0.0.0`): override the bind address.
- `PORT` (default `8000`): override the port.
- `MEDIA_ROOT` (default `<project>/media`): custom path for uploaded media.
- `MPV_EXTRA_ARGS`: additional whitespace-delimited flags passed to `mpv` for every playback.
- `MPV_AUDIO_DEVICE`: optional mpv audio device string (e.g. `alsa/hdmi:CARD=vc4hdmi0,DEV=0`).
- `AUTO_START_LAST`: set to `1`, `true`, or `yes` to automatically resume the last-played item when the server starts.

## Projector playback notes

The server spawns `mpv` in fullscreen mode to handle both images and videos. Videos loop indefinitely (`--loop=inf`). Images rely on `--loop-file=inf` and `--image-display-duration=inf` to remain on screen without flashing between transitions. If you need DRM/KMS output without X, export `MPV_EXTRA_ARGS="--gpu-context=drm --vo=gpu"` before launching the service.

For HDMI audio, run `mpv --audio-device=help` once to list available sinks, then set `MPV_AUDIO_DEVICE` to the desired entry (for example `alsa/hdmi:CARD=vc4hdmi0,DEV=0`).

## Projector power scheduling

The UI now includes a "Projector power schedule" card where you can enable automatic HDMI-CEC power on and off times. When either action is enabled, the backend stores the schedule in `media/projector_schedule.json` and runs a lightweight background scheduler that sends the corresponding CEC command each day.

The controller uses [`cec-ctl`](https://github.com/cec-o-matic/cec-o-matic/wiki/Cec-ctl) by default. You can customise the CEC invocation with environment variables:

- `PROJECTOR_CEC_TOOL` (default `cec-ctl`) – executable used to send CEC commands.
- `PROJECTOR_CEC_DEVICE` (optional) – path to the CEC device (for example `/dev/cec0`).
- `PROJECTOR_CEC_LOGICAL_ADDR` (default `0`) – logical address of the projector/TV to target.
- `PROJECTOR_CEC_POWER_ON_ARGS` / `PROJECTOR_CEC_POWER_OFF_ARGS` – override the specific arguments passed for power on/off. Each value is tokenised with shell-style rules (e.g. `--wake` or `-s --osd-string "Pi Show"`). When unset, the defaults send `--wake` / `--standby` with `cec-ctl`.

If you need to trigger the projector manually, use the "Turn on now" / "Turn off now" buttons in the UI or call the `/api/projector/power` endpoint described below.

## Auto-start on boot

1. Enable remembering the last played item by exporting `AUTO_START_LAST=1` in the service environment.
2. Create a `systemd` service (as user `pi`) at `/etc/systemd/system/pishow.service`:

   ```ini
   [Unit]
   Description=PISHOW media controller
   After=network-online.target
   Wants=network-online.target

   [Service]
   Type=simple
   User=pi
   WorkingDirectory=/home/pi/PISHOW
   Environment="AUTO_START_LAST=1"
   Environment="MPV_EXTRA_ARGS=--gpu-context=drm --vo=gpu"
   Environment="MPV_AUDIO_DEVICE=alsa/hdmi:CARD=vc4hdmi0,DEV=0"
   ExecStart=/usr/bin/python3 -m backend.app
   Restart=always
   RestartSec=2

   [Install]
   WantedBy=multi-user.target
   ```

3. Reload and enable the service:

   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now pishow.service
   ```

When the Raspberry Pi reboots, the service will restart the Flask server, which in turn restarts the last projection automatically if `AUTO_START_LAST` is set.

## API quick reference

- `GET /api/media` – List gallery entries.
- `POST /api/media` – Upload a file using `multipart/form-data` with field `file`.
- `POST /api/media/upload-and-play` – Upload a file (multipart or JSON base64) and immediately start playback.
- `DELETE /api/media/<id>` – Remove media and the underlying file.
- `POST /api/media/<id>/play` – Send media to the projector.
- `POST /api/stop` – Stop playback.
- `GET /api/status` – Retrieve current playback status.
- `POST /api/projector/power` – Send JSON `{"state": "on"}` or `{"state": "off"}` to control the projector via CEC.
- `GET /api/projector/schedule` – Retrieve the current projector power schedule.
- `PUT /api/projector/schedule` – Update the schedule by sending `{ "power_on": {"enabled": bool, "time": "HH:MM"|null}, "power_off": {...} }`.
- `GET /media/<filename>` – Serve uploaded files (used by the web UI for previews).

## File layout

- `backend/app.py` – Flask application and API endpoints.
- `backend/media_manager.py` – Media metadata storage and gallery persistence.
- `backend/playback.py` – Wrapper around the `mpv` subprocess.
- `backend/templates/index.html` – Web interface markup.
- `backend/static/app.js` – Front-end logic for uploads and playback control.
- `backend/static/styles.css` – UI styling.
- `media/` – Uploaded files and gallery metadata (`gallery.json`).

## Maintenance

- Uploaded files live inside the `media/` directory by default; ensure the partition has enough space for your assets.
- Back up `media/gallery.json` to preserve the gallery metadata if you migrate to another Pi.
- To clear the gallery, stop the service, delete the contents of `media/`, and remove `gallery.json`.
- For troubleshooting, run the server in a shell to see Flask logs and `mpv` start/stop events.
- To call `POST /api/media/upload-and-play` with JSON, send `{"filename": "example.jpg", "content": "<base64>"}` (optionally `content_type`). The server stores the asset in the gallery, starts playback via `mpv`, and returns the new media record with `status: "playing"`.
