# PISHOW

A lightweight Flask application to manage a media gallery of images and videos and control what plays on a projector connected to a Raspberry Pi.

## Features

- Upload images and videos (configurable upload limit, default 512 MB)
- Organise media in a library with default durations for images
- Build playlists that mix images and videos in any order
- Send playlists to the projector display, with polling to pick up changes automatically
- Infinite display for single-image playlists; configurable durations for multi-image playlists

## Requirements

- Raspberry Pi OS 64-bit (Lite works fine) with Python 3.11+
- `pip`, `virtualenv`, and `git` installed
- Projector connected to the Pi (HDMI)

## Installation

```sh
sudo apt update
sudo apt install -y python3-venv python3-pip git ffmpeg

cd /opt
sudo git clone https://example.com/PISHOW.git
sudo chown -R $USER:$USER PISHOW
cd PISHOW

python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Initialize the database
FLASK_APP=pishow.py flask --app pishow.py run --no-debugger --reload
# On first run the database is created automatically; stop with Ctrl+C when ready.
```

> **Media storage**: By default uploaded media is stored in the `media/` folder inside the project. Set `PISHOW_MEDIA_ROOT=/path/to/storage` before starting the app to use a different location (e.g. an external drive).

## Running the App

```sh
source /opt/PISHOW/.venv/bin/activate
export FLASK_APP=pishow.py
export PISHOW_MEDIA_ROOT=/opt/PISHOW/media  # optional override
export PISHOW_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex())')"
flask run --host=0.0.0.0 --port=8000
```

- Visit `http://<pi-ip>:8000/` from a laptop/tablet to access the control panel.
- Open `http://<pi-ip>:8000/display` in Chromium (or full-screen kiosk browser) on the Pi connected to the projector.

### Autostart Suggestions

1. Install Chromium if you want a kiosk window:
   ```sh
   sudo apt install -y chromium-browser
   ```

2. Create a systemd service `/etc/systemd/system/pishow.service` (requires sudo):
   ```ini
   [Unit]
   Description=PISHOW media server
   After=network.target

   [Service]
   User=pi
   WorkingDirectory=/opt/PISHOW
   Environment="FLASK_APP=pishow.py"
   Environment="PISHOW_MEDIA_ROOT=/opt/PISHOW/media"
   ExecStart=/opt/PISHOW/.venv/bin/flask run --host=0.0.0.0 --port=8000
   Restart=on-failure

   [Install]
   WantedBy=multi-user.target
   ```

   Enable it:
   ```sh
   sudo systemctl enable --now pishow.service
   ```

3. Launch the projector browser in kiosk mode on boot by adding a script (optional).

## Folder Structure

```
app/
  __init__.py
  db.py
  routes.py
  services.py
  templates/
    base.html
    admin.html
    display.html
  static/
    css/site.css
    js/admin.js
    js/display.js
media/               # default upload directory
instance/            # holds the SQLite database
pishow.py            # Flask entry point
requirements.txt
README.md
```

## API Overview

- `POST /api/media` – upload a file (multipart form field `file`).
- `GET /api/media` – list library entries.
- `DELETE /api/media/<id>` – remove media (and file).
- `POST /api/media/<id>/duration` – set default image duration.
- `GET /api/playlist` – retrieve active playlist and version.
- `POST /api/playlist` – set playlist order and durations.
- `DELETE /api/playlist` – clear playlist.

## Notes

- Videos play until completion before advancing.
- Multi-image playlists respect per-item durations.
- Single-image playlists show indefinitely (duration `null`).
- The display client polls every 5 seconds for updates; adjust in `app/static/js/display.js` if needed.

## Development

```sh
pip install -r requirements.txt
flask --app pishow.py run --debug
```
