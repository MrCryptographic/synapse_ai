import json
import os
from pathlib import Path

from flask import Blueprint, abort, current_app, render_template, session


moderation_blueprint = Blueprint("roleplay_moderation", __name__)


def is_moderator(user_id):
    if not user_id:
        return False
    configured_ids = current_app.config.get("ROLEPLAY_MODERATOR_IDS", set())
    if user_id in configured_ids:
        return True

    users_file = Path(current_app.config["USER_DB_FILE"])
    try:
        users = json.loads(users_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    records = users.get("users", {}) if isinstance(users, dict) else {}
    return any(
        isinstance(user, dict)
        and user.get("id") == user_id
        and user.get("role") == "moderator"
        for user in records.values()
    )


@moderation_blueprint.get("/approvelibrary")
def approval_page():
    if not is_moderator(session.get("user_id")):
        abort(403)
    return render_template("approvelibrary.html", csrf_token=session.get("csrf_token", ""))