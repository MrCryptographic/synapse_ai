# Synapse AI

A self-hosted AI chat interface that runs on your machine and lets anyone on your local network use it through a browser — no accounts, no cloud, no subscriptions.

Built on top of [LM Studio](https://lmstudio.ai/)'s local API server. Synapse is the front door to whatever models you have downloaded.

![Python](https://img.shields.io/badge/Python-3.8+-blue?style=flat-square&logo=python)
![Flask](https://img.shields.io/badge/Flask-3.x-black?style=flat-square&logo=flask)
![LM Studio](https://img.shields.io/badge/LM%20Studio-required-orange?style=flat-square)

---

## What it does

- **Shared access** — run it once on your machine, anyone on your Wi-Fi opens the page and starts chatting
- **Chat history** — conversations are saved server-side in a JSON file, so they survive browser refreshes and cookie clears
- **Model switching** — swap between any model you have downloaded in LM Studio without touching the app
- **Model nicknames** — give your models friendly names (e.g. rename `gemma-4-e4b-Q4_K_M` to `Basically Gemini`) — nicknames are per-browser and never leave your device
- **System prompt & generation params** — tweak temperature, top-p, top-k, repeat penalty, max tokens, and seed from a dedicated settings panel
- **Quick presets** — one-click Precise / Balanced / Creative configurations
- **Markdown rendering** — AI responses render with full markdown including code blocks
- **Live resource usage** — CPU and RAM displayed in the sidebar, updated in real time over WebSocket
- **Host notifications** — desktop alerts on your machine whenever a generation starts, showing the model name and time
- **Boop button** — lets any network user send a notification ping to the host machine
- **Feedback system** — users can submit feedback with an optional name; saved to a local JSON file
- **Model filtering** — hide specific models from the UI by keyword (useful for keeping private models private)
- **Responsive design** — works on phones and tablets with a slide-out sidebar

---

## Requirements

- [LM Studio](https://lmstudio.ai/) installed with at least one model downloaded
- Python 3.8 or higher
- pip

---

## Project structure

```
synapse_ai/
├── app.py                  # Flask backend
├── requirements.txt        # Python dependencies
├── conversations.json      # Auto-created on first run
├── feedback.json           # Auto-created on first feedback submission
├── templates/
│   └── index.html          # Frontend (single file)
└── static/
    └── icons/
        ├── regenerate.svg
        ├── feedback.svg
        └── boop.svg
```

---

## Quick setup (recommended)

Three scripts are included — pick the one for your platform. Each one clones the repo, installs dependencies into a virtual environment, and drops a launch shortcut. You only need to run it once.

| Platform | Script | How to run |
|---|---|---|
| **Windows** | `setup.bat` | Double-click it |
| **Mac / Linux** | `setup.sh` | `chmod +x setup.sh && ./setup.sh` |
| **Any (Python)** | `setup.py` | `python setup.py` |

After setup finishes, use the generated `launch_synapse.bat` / `launch_synapse.sh` to start Synapse from then on.

> The shell and Python scripts automatically create a virtual environment (`.venv`) inside the project folder so nothing pollutes your global Python install.

---

## Manual setup

### 1. Clone the repo

```bash
git clone https://github.com/yourusername/synapse-ai.git
cd synapse-ai/synapse_ai
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

The `requirements.txt` includes:

```
Flask
requests
plyer
psutil
Flask-SocketIO
```

> **Note for Linux users:** `plyer` desktop notifications may require additional setup depending on your desktop environment. On headless servers, notifications will silently fail — everything else still works.

### 3. Configure LM Studio

Open LM Studio and do the following:

1. Go to the **Local Server** tab (the `<->` icon on the left sidebar)
2. Click **Start Server**
3. Change the **Host** dropdown from `localhost` to `0.0.0.0`
   - This allows LM Studio to accept connections from Synapse, not just from itself
4. Leave the port at `1234` (default)

> If you skip step 3, Synapse will work on your own machine but will fail to reach LM Studio from the Flask server process.

### 4. Run Synapse

```bash
python app.py
```

You should see output like:

```
 * Running on http://0.0.0.0:5000
```

### 5. Open the app

- **On your machine:** http://localhost:5000
- **On any other device on the same Wi-Fi:** http://YOUR_LOCAL_IP:5000

To find your local IP:
- **Windows:** run `ipconfig` in Command Prompt, look for `IPv4 Address`
- **Mac/Linux:** run `ifconfig` or `ip addr`, look for something like `192.168.x.x`

---

## Hiding models from the UI

If you have models you don't want showing up for network users (e.g. models with sensitive names), add keywords to the `MODEL_IGNORE_LIST` near the top of `app.py`:

```python
MODEL_IGNORE_LIST = [
    "nsfw",
    "uncensored",
    "roleplay",
    "text"
]
```

Any model whose ID contains one of these strings (case-insensitive) will be silently excluded from the dropdown.

---

## Changing the port

If port 5000 is already in use, edit the last line of `app.py`:

```python
socketio.run(app, host='0.0.0.0', port=5000, debug=False)
#                                  ^^^^ change this
```

---

## Running on startup (optional)

### Windows — Task Scheduler

1. Open **Task Scheduler** and create a new Basic Task
2. Set trigger to **At log on**
3. Set action to **Start a program**
   - Program: `python`
   - Arguments: `app.py`
   - Start in: `C:\path\to\synapse_ai`

### Mac/Linux — systemd or launchd

A minimal systemd service example:

```ini
[Unit]
Description=Synapse AI
After=network.target

[Service]
WorkingDirectory=/path/to/synapse_ai
ExecStart=/usr/bin/python3 app.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Save it to `/etc/systemd/system/synapse.service`, then:

```bash
sudo systemctl enable synapse
sudo systemctl start synapse
```

---

## Notes

- **Conversations** are stored in `conversations.json` in the project folder. Back this up if you care about history.
- **Model nicknames** are per-browser and session-only — they reset on page refresh by design, so nothing sensitive gets stored.
- **First response slowness** is normal — LM Studio loads the model into RAM/VRAM on demand. Subsequent messages in the same session are much faster.
- **VRAM stats** display as `N/A` by default. LM Studio doesn't currently expose VRAM usage through its API.
- The app runs in production mode (`debug=False`). Don't expose port 5000 to the public internet without adding authentication.

---

## Troubleshooting

**"Error loading models" in the dropdown**
LM Studio's server isn't running, or it's still bound to `localhost`. Check step 3 of setup.

**Works on my machine but not on other devices**
Make sure LM Studio's host is set to `0.0.0.0`, not `localhost` or `127.0.0.1`. Also check that your firewall isn't blocking port 5000.

**First message never responds / times out**
The model is still loading. Large models can take 30–60 seconds on first load. Wait and try again — subsequent messages will be fast.

**Desktop notifications not working**
On some Linux setups, `plyer` needs `notify-send` or a D-Bus notification daemon. On macOS, you may need to grant terminal notification permissions in System Settings. Notifications are cosmetic — the app works without them.

**Port 5000 conflict on Mac**
macOS Monterey and later uses port 5000 for AirPlay Receiver. Either disable AirPlay Receiver in System Settings → General → AirDrop & Handoff, or change Synapse's port to something else like 5001.

---

## License

MIT — do whatever you want with it.