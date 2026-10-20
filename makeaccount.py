#!/usr/bin/env python3
"""Create a Synapse account from the terminal."""

import getpass
import hashlib
import json
import os
import re
import secrets
import tempfile
import uuid
from pathlib import Path


PASSWORD_HASH_ITERATIONS = 600_000
APP_DIR = Path(__file__).resolve().parent
USER_DB_FILE = APP_DIR / "users.json"
CONV_DB_FILE = APP_DIR / "conversations.json"


def read_json(path, default):
    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError:
        return default


def write_json_atomically(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as file:
            temp_path = Path(file.name)
            json.dump(data, file, indent=2, ensure_ascii=False)
            file.write("\n")
        os.replace(temp_path, path)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()


def password_hash(password, salt):
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_HASH_ITERATIONS,
    ).hex()


def main():
    new_database = not USER_DB_FILE.exists()
    if not new_database:
        users_data = read_json(USER_DB_FILE, None)
        if not isinstance(users_data, dict) or not isinstance(users_data.get("users"), dict):
            raise ValueError(f"{USER_DB_FILE} has an invalid account database format.")
    else:
        users_data = {"users": {}}

    username = input("Username (3-32 letters, numbers, ., _, or -): ").strip().lower()
    if not re.fullmatch(r"[a-z0-9_.-]{3,32}", username):
        raise ValueError("Username must be 3-32 letters, numbers, dots, underscores, or hyphens.")
    if username in users_data["users"]:
        raise ValueError(f"The username '{username}' is already registered.")

    password = getpass.getpass("Password (at least 12 characters): ")
    if len(password) < 12:
        raise ValueError("Password must be at least 12 characters.")
    if len(password.encode("utf-8")) > 1024:
        raise ValueError("Password must be no longer than 1024 UTF-8 bytes.")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        raise ValueError("Passwords do not match.")

    salt = secrets.token_bytes(16)
    users_data["users"][username] = {
        "id": str(uuid.uuid4()),
        "salt": salt.hex(),
        "password_hash": password_hash(password, salt),
    }
    if new_database and CONV_DB_FILE.exists():
        conversations = read_json(CONV_DB_FILE, {})
        if not isinstance(conversations, dict):
            raise ValueError(f"{CONV_DB_FILE} must contain a JSON object.")
        owned_conversations = {
            conversation_id: conversation
            for conversation_id, conversation in conversations.items()
            if isinstance(conversation, dict) and conversation.get("owner_id")
        }
        write_json_atomically(CONV_DB_FILE, owned_conversations)
    write_json_atomically(USER_DB_FILE, users_data)
    print(f"Account '{username}' created. You can now sign in through the Synapse web page.")


if __name__ == "__main__":
    try:
        main()
    except (EOFError, KeyboardInterrupt):
        print("\nAccount creation cancelled.")
        raise SystemExit(1)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"Could not create account: {error}")
        raise SystemExit(1)
