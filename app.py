import json
import hashlib
import hmac
import os
import secrets
import re
import uuid
import requests
import datetime
import time
import threading
from pathlib import Path
from flask import Flask, request, jsonify, render_template, redirect, session, url_for
from flask_socketio import SocketIO
from plyer import notification
import psutil

# --- Configuration ---
LM_STUDIO_URL_BASE = "http://localhost:1234/v1"
CONV_DB_FILE = "conversations.json"
FEEDBACK_DB_FILE = "feedback.json"
USER_DB_FILE = "users.json"
PASSWORD_HASH_ITERATIONS = 600_000


# List of keywords to filter out unwanted models from LM Studio's response
MODEL_IGNORE_LIST = [
]

# --- App Initialization ---
app = Flask(__name__)


def load_or_create_secret_key():
    configured_key = os.environ.get("SYNAPSE_SECRET_KEY")
    if configured_key:
        return configured_key

    key_path = Path(__file__).with_name(".synapse_secret_key")
    try:
        key = key_path.read_text(encoding="ascii").strip()
    except FileNotFoundError:
        generated_key = secrets.token_hex(32)
        try:
            file_descriptor = os.open(
                key_path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
        except FileExistsError:
            key = key_path.read_text(encoding="ascii").strip()
        else:
            with os.fdopen(file_descriptor, "w", encoding="ascii") as key_file:
                key_file.write(generated_key)
            key = generated_key
    if not key:
        raise RuntimeError(f"The session signing key file is empty: {key_path}")
    return key


app.secret_key = load_or_create_secret_key()
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("SYNAPSE_COOKIE_SECURE", "").lower() in ("1", "true", "yes"),
    PERMANENT_SESSION_LIFETIME=datetime.timedelta(hours=12),
)
socketio = SocketIO(app)
user_db_lock = threading.Lock()


def csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


def public_csrf_token():
    payload = f"{int(time.time())}:{secrets.token_urlsafe(32)}"
    signature = hmac.new(
        app.secret_key.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{payload}:{signature}"


def is_valid_public_csrf_token(token):
    try:
        timestamp, nonce, supplied_signature = token.split(":", 2)
        token_time = int(timestamp)
    except (AttributeError, ValueError):
        return False
    if not nonce or not 0 <= time.time() - token_time <= 3600:
        return False
    payload = f"{timestamp}:{nonce}"
    expected_signature = hmac.new(
        app.secret_key.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(supplied_signature, expected_signature)


def load_user_db():
    try:
        with open(USER_DB_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def save_user_db(data):
    with open(USER_DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def initialize_user_db():
    users = load_user_db()
    if users is not None:
        return users
    conversations = load_json_db(CONV_DB_FILE)
    save_json_db(
        {
            conversation_id: conversation
            for conversation_id, conversation in conversations.items()
            if conversation.get("owner_id")
        },
        CONV_DB_FILE,
    )
    users = {"users": {}}
    save_user_db(users)
    return users


def normalize_username(username):
    return username.strip().lower()


def hash_password(password, salt):
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_HASH_ITERATIONS
    )


def get_current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    users = load_user_db()
    if users is None:
        return None
    return next(
        (user for user in users.get("users", {}).values() if user["id"] == user_id),
        None,
    )


def get_owned_conversation(conversations, conversation_id):
    conversation = conversations.get(conversation_id)
    if conversation is None or conversation.get("owner_id") != session.get("user_id"):
        return None
    return conversation


@app.before_request
def require_authentication():
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        supplied_token = request.headers.get("X-CSRF-Token")
        if request.endpoint in ("login", "register"):
            supplied_token = request.form.get("csrf_token")
            valid_token = is_valid_public_csrf_token(supplied_token)
        else:
            if request.endpoint == "logout":
                supplied_token = request.form.get("csrf_token")
            expected_token = session.get("csrf_token")
            valid_token = (
                supplied_token is not None
                and expected_token is not None
                and hmac.compare_digest(supplied_token, expected_token)
            )
        if not valid_token:
            if request.endpoint == "register":
                return render_template(
                    "register.html",
                    csrf_token=public_csrf_token(),
                    signup_error="The signup form is invalid or expired. Reload the page and try again.",
                ), 400
            if request.endpoint == "login":
                return render_template(
                    "login.html",
                    csrf_token=public_csrf_token(),
                    error="The sign-in form is invalid or expired. Reload the page and try again.",
                ), 400
            return jsonify({"error": "Invalid or missing CSRF token."}), 400

    if request.endpoint in ("login", "register", "static"):
        return None
    if get_current_user() is None:
        session.clear()
        if request.path.startswith("/api/"):
            return jsonify({"error": "Authentication required."}), 401
        return redirect(url_for("login"))


@app.after_request
def set_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    if request.path in ("/", "/login", "/register") or request.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@socketio.on("connect")
def authenticate_socket():
    if get_current_user() is None:
        return False


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        if get_current_user() is not None:
            return redirect(url_for("index"))
        return render_template(
            "login.html", csrf_token=public_csrf_token(), error=None
        )

    username = normalize_username(request.form.get("username", ""))
    password = request.form.get("password", "")
    users = load_user_db()
    user = users.get("users", {}).get(username) if users else None
    if len(password.encode("utf-8")) > 1024:
        return render_template(
            "login.html", csrf_token=public_csrf_token(),
            error="Invalid username or password."
        ), 401
    salt = bytes.fromhex(user["salt"]) if user else b"synapse-login-check"
    candidate_hash = hash_password(password, salt)
    if user and hmac.compare_digest(candidate_hash.hex(), user["password_hash"]):
        session.clear()
        session["user_id"] = user["id"]
        session["csrf_token"] = secrets.token_urlsafe(32)
        session.permanent = True
        return redirect(url_for("index"))
    return render_template(
        "login.html", csrf_token=public_csrf_token(), error="Invalid username or password."
    ), 401


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        if get_current_user() is not None:
            return redirect(url_for("index"))
        return render_template("register.html", csrf_token=public_csrf_token(), signup_error=None)

    username = normalize_username(request.form.get("username", ""))
    password = request.form.get("password", "")
    if not re.fullmatch(r"[a-z0-9_.-]{3,32}", username):
        return render_template(
            "register.html", csrf_token=public_csrf_token(),
            signup_error="Use 3–32 letters, numbers, dots, underscores, or hyphens for your username."
        ), 400
    if len(password) < 12:
        return render_template(
            "register.html", csrf_token=public_csrf_token(),
            signup_error="Choose a password with at least 12 characters."
        ), 400
    if len(password.encode("utf-8")) > 1024:
        return render_template(
            "register.html", csrf_token=public_csrf_token(),
            signup_error="Choose a password no longer than 1024 UTF-8 bytes."
        ), 400

    with user_db_lock:
        users = initialize_user_db()
        if username in users["users"]:
            return render_template(
                "register.html", csrf_token=public_csrf_token(),
                signup_error="That username is already registered."
            ), 409
        salt = secrets.token_bytes(16)
        users["users"][username] = {
            "id": str(uuid.uuid4()),
            "salt": salt.hex(),
            "password_hash": hash_password(password, salt).hex(),
        }
        save_user_db(users)

    session.clear()
    session["user_id"] = users["users"][username]["id"]
    session["csrf_token"] = secrets.token_urlsafe(32)
    session.permanent = True
    return redirect(url_for("index"))


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))

# --- Data Persistence Functions ---
def load_json_db(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {} if 'conversations' in filepath else []

def save_json_db(data, filepath):
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# --- Host Notification ---
def send_host_notification(title, message):
    try:
        notification.notify(
            title=title,
            message=message,
            app_name='Synapse',
            timeout=10
        )
    except Exception as e:
        print(f"Could not send notification: {e}")

# --- Resource Monitoring ---
def send_stats():
    with app.app_context():
        while True:
            stats = {
                'cpu': psutil.cpu_percent(),
                'ram': psutil.virtual_memory().percent,
                'vram': "N/A"
            }
            socketio.emit('update_stats', stats)
            time.sleep(2)

stats_thread = threading.Thread(target=send_stats, daemon=True)
stats_thread.start()

# --- API Endpoints ---
@app.route('/')
def index():
    return render_template('index.html', csrf_token=csrf_token())

@app.route('/api/models', methods=['GET'])
def get_models():
    try:
        response = requests.get(f"{LM_STUDIO_URL_BASE}/models")
        response.raise_for_status()
        all_models = response.json().get('data', [])
        filtered_ids = [
            model['id'] for model in all_models
            if not any(keyword.lower() in model['id'].lower() for keyword in MODEL_IGNORE_LIST)
        ]
        return jsonify(filtered_ids)
    except Exception as e:
        return jsonify({"error": f"Could not fetch models: {e}"}), 500

@app.route('/api/boop', methods=['POST'])
def boop():
    send_host_notification(
        title="BEEP BEEP! You've been booped!",
        message="Someone on the network pressed the Boop button."
    )
    return jsonify({"success": True})

def get_ai_response(history, model_name, temperature=0.7, top_p=1.0, max_tokens=-1, frequency_penalty=0.0, presence_penalty=0.0):
    current_time = datetime.datetime.now().strftime("%I:%M:%S %p")
    send_host_notification(
        title="Synapse: AI Generation Started",
        message=f"Model: {model_name.split('/')[-1]}\nTime: {current_time}"
    )
    body = {"model": model_name, "messages": history, "temperature": temperature, "top_p": top_p, "frequency_penalty": frequency_penalty, "presence_penalty": presence_penalty}
    if max_tokens > 0:
        body["max_tokens"] = max_tokens
    response = requests.post(
        f"{LM_STUDIO_URL_BASE}/chat/completions",
        json=body
    )
    response.raise_for_status()
    content = response.json()['choices'][0]['message']['content']
    return re.sub(r'<think>[\s\S]*?<\/think>\s*', '', content, flags=re.DOTALL).strip()

@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.json
    conv_id, prompt, model = data.get('conversation_id'), data.get('prompt'), data.get('model')
    temperature = data.get('temperature', 0.7)
    top_p = data.get('top_p', 1.0)
    max_tokens = data.get('max_tokens', -1)
    frequency_penalty = data.get('frequency_penalty', 0.0)
    presence_penalty = data.get('presence_penalty', 0.0)
    convs = load_json_db(CONV_DB_FILE)
    conversation = get_owned_conversation(convs, conv_id)
    if conversation is None:
        return jsonify({"error": "Conversation not found."}), 404
    history = conversation['messages']
    history.append({"role": "user", "content": prompt})
    try:
        ai_content = get_ai_response(history, model, temperature, top_p, max_tokens, frequency_penalty, presence_penalty)
        history.append({"role": "assistant", "content": ai_content})
        if len([m for m in history if m['role'] == 'user']) == 1:
            conversation['title'] = prompt
        save_json_db(convs, CONV_DB_FILE)
        return jsonify({"role": "assistant", "content": ai_content})
    except Exception as e:
        history.pop()
        save_json_db(convs, CONV_DB_FILE)
        return jsonify({"error": f"Error contacting LM Studio: {e}"}), 500

@app.route('/api/regenerate', methods=['POST'])
def regenerate():
    data = request.json
    conv_id, model = data.get('conversation_id'), data.get('model')
    temperature = data.get('temperature', 0.7)
    top_p = data.get('top_p', 1.0)
    max_tokens = data.get('max_tokens', -1)
    frequency_penalty = data.get('frequency_penalty', 0.0)
    presence_penalty = data.get('presence_penalty', 0.0)
    convs = load_json_db(CONV_DB_FILE)
    conversation = get_owned_conversation(convs, conv_id)
    if conversation is None:
        return jsonify({"error": "Conversation not found."}), 404
    history = conversation['messages']
    if history and history[-1]['role'] == 'assistant': history.pop()
    try:
        ai_content = get_ai_response(history, model, temperature, top_p, max_tokens, frequency_penalty, presence_penalty)
        history.append({"role": "assistant", "content": ai_content})
        save_json_db(convs, CONV_DB_FILE)
        return jsonify({"role": "assistant", "content": ai_content})
    except Exception as e:
        return jsonify({"error": f"Error contacting LM Studio: {e}"}), 500

@app.route('/api/general-feedback', methods=['POST'])
def general_feedback():
    data = request.json
    feedback_log = load_json_db(FEEDBACK_DB_FILE)
    feedback_log.append({
        "name": data.get('name', 'Anonymous'),
        "feedback": data.get('feedback'),
        "timestamp": datetime.datetime.utcnow().isoformat()
    })
    save_json_db(feedback_log, FEEDBACK_DB_FILE)
    return jsonify({"success": True})

@app.route('/api/conversations', methods=['GET'])
def get_conversations():
    convs = load_json_db(CONV_DB_FILE)
    conv_list = [
        {"id": conv_id, "title": details.get("title", "New Chat")}
        for conv_id, details in convs.items()
        if details.get("owner_id") == session["user_id"]
    ]
    return jsonify(sorted(conv_list, key=lambda x: convs[x['id']]['timestamp'], reverse=True))

@app.route('/api/conversations', methods=['POST'])
def create_conversation():
    convs = load_json_db(CONV_DB_FILE)
    conv_id = str(uuid.uuid4())
    convs[conv_id] = {
        "title": "New Chat",
        "messages": [],
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "owner_id": session["user_id"],
    }
    save_json_db(convs, CONV_DB_FILE)
    return jsonify({"id": conv_id, "title": "New Chat"})

@app.route('/api/conversations/<conv_id>', methods=['GET'])
def get_conversation_details(conv_id):
    convs = load_json_db(CONV_DB_FILE)
    conversation = get_owned_conversation(convs, conv_id)
    if conversation is None:
        return jsonify({"error": "Conversation not found."}), 404
    return jsonify(conversation.get('messages', []))

@app.route('/api/conversations/<conv_id>', methods=['DELETE'])
def delete_conversation(conv_id):
    convs = load_json_db(CONV_DB_FILE)
    if get_owned_conversation(convs, conv_id) is None:
        return jsonify({"error": "Conversation not found."}), 404
    del convs[conv_id]
    save_json_db(convs, CONV_DB_FILE)
    return jsonify({"success": True})

@app.route('/api/conversations/<conv_id>', methods=['PUT'])
def rename_conversation(conv_id):
    data = request.json
    new_title = data.get('title')
    convs = load_json_db(CONV_DB_FILE)
    conversation = get_owned_conversation(convs, conv_id)
    if conversation is None:
        return jsonify({"error": "Conversation not found."}), 404
    conversation['title'] = new_title
    save_json_db(convs, CONV_DB_FILE)
    return jsonify({"success": True, "title": new_title})

if __name__ == '__main__':
    socketio.run(
        app,
        host=os.environ.get("SYNAPSE_HOST", "127.0.0.1"),
        port=int(os.environ.get("SYNAPSE_PORT", "6767")),
        debug=False,
    )