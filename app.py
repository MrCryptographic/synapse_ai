import json
import uuid
import requests
import datetime
import re
import time
import threading
from flask import Flask, request, jsonify, render_template
from flask_socketio import SocketIO
from plyer import notification
import psutil

# --- Configuration ---
LM_STUDIO_URL_BASE = "http://localhost:1234/v1"
CONV_DB_FILE = "conversations.json"
FEEDBACK_DB_FILE = "feedback.json"


# List of keywords to filter out unwanted models from LM Studio's response
MODEL_IGNORE_LIST = [
]

# --- App Initialization ---
app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

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
    return render_template('index.html')

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
    history = convs[conv_id]['messages']
    history.append({"role": "user", "content": prompt})
    try:
        ai_content = get_ai_response(history, model, temperature, top_p, max_tokens, frequency_penalty, presence_penalty)
        history.append({"role": "assistant", "content": ai_content})
        if len([m for m in history if m['role'] == 'user']) == 1:
            convs[conv_id]['title'] = prompt
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
    history = convs[conv_id]['messages']
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
    conv_list = [{"id": conv_id, "title": details.get("title", "New Chat")} for conv_id, details in convs.items()]
    return jsonify(sorted(conv_list, key=lambda x: convs[x['id']]['timestamp'], reverse=True))

@app.route('/api/conversations', methods=['POST'])
def create_conversation():
    convs = load_json_db(CONV_DB_FILE)
    conv_id = str(uuid.uuid4())
    convs[conv_id] = {"title": "New Chat", "messages": [], "timestamp": datetime.datetime.utcnow().isoformat()}
    save_json_db(convs, CONV_DB_FILE)
    return jsonify({"id": conv_id, "title": "New Chat"})

@app.route('/api/conversations/<conv_id>', methods=['GET'])
def get_conversation_details(conv_id):
    convs = load_json_db(CONV_DB_FILE)
    return jsonify(convs.get(conv_id, {}).get('messages', []))

@app.route('/api/conversations/<conv_id>', methods=['DELETE'])
def delete_conversation(conv_id):
    convs = load_json_db(CONV_DB_FILE)
    if conv_id in convs: del convs[conv_id]
    save_json_db(convs, CONV_DB_FILE)
    return jsonify({"success": True})

@app.route('/api/conversations/<conv_id>', methods=['PUT'])
def rename_conversation(conv_id):
    data = request.json
    new_title = data.get('title')
    convs = load_json_db(CONV_DB_FILE)
    if conv_id in convs: convs[conv_id]['title'] = new_title
    save_json_db(convs, CONV_DB_FILE)
    return jsonify({"success": True, "title": new_title})

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=6767, debug=False)