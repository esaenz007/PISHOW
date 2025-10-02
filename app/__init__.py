import os
from flask import Flask


def create_app():
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("PISHOW_SECRET_KEY", "dev"),
        DATABASE=os.path.join(app.instance_path, "pishow.sqlite3"),
        MEDIA_ROOT=os.path.abspath(
            os.environ.get(
                "PISHOW_MEDIA_ROOT",
                os.path.join(os.path.dirname(__file__), "..", "media"),
            )
        ),
        MAX_CONTENT_LENGTH=512 * 1024 * 1024,
        ALLOWED_IMAGE_EXTENSIONS={"jpg", "jpeg", "png", "gif", "bmp", "webp"},
        ALLOWED_VIDEO_EXTENSIONS={"mp4", "mov", "avi", "mkv", "webm", "m4v"},
    )

    os.makedirs(app.instance_path, exist_ok=True)
    os.makedirs(app.config["MEDIA_ROOT"], exist_ok=True)

    from . import db, routes  # pylint: disable=import-outside-toplevel

    db.init_app(app)
    with app.app_context():
        db.init_db()
    routes.init_app(app)

    return app
