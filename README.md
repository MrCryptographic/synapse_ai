# Synapse AI

A self-hosted AI chat interface that runs on your machine and lets authorized users chat through a browser — no cloud, no subscriptions.

Built on top of [LM Studio](https://lmstudio.ai/)'s local API server. Synapse is the front door to whatever models you have downloaded.

![Python](https://img.shields.io/badge/Python-3.8+-blue?style=flat-square&logo=python)
![Flask](https://img.shields.io/badge/Flask-3.x-black?style=flat-square&logo=flask)
![LM Studio](https://img.shields.io/badge/LM%20Studio-required-orange?style=flat-square)

---

## What it does

- **Individual accounts** — each account has its own private conversation list and history
- **Account deletion** — permanently remove your account and its conversations after confirming your current password
- **Chat history** — conversations are saved server-side in a JSON file, so they survive browser refreshes and cookie clears
- **Model switching** — swap between any model you have downloaded in LM Studio without touching the app
- **Color themes** — choose Ember, Ocean, Forest, Violet, or Rose from Settings; your choice is saved in your browser
- **Response streaming** — optionally display model responses token by token from Settings; the preference is saved in your browser
- **Editable prompts** — edit a user message to discard later turns and regenerate from the revised prompt
- **Message copying** — copy user prompts or assistant responses from the message actions
- **Message appearance** — choose bubble, clean, or soft-card layouts and sans, serif, or monospace text
- **Keyboard controls** — Enter sends, Ctrl+Enter regenerates the latest response, and Shift+Enter adds a line; Markdown shortcuts format selected text
- **GPU memory monitoring** — reports VRAM when `nvidia-smi` or `rocm-smi` is available on the host
- **Model nicknames** — give your models friendly names (e.g. rename `gemma-4-e4b-Q4_K_M` to `Basically Gemini`) — nicknames are per-browser and never leave your device
- **System prompt & generation params** — tweak temperature, top-p, top-k, repeat penalty, max tokens, and seed from a dedicated settings panel
- **Quick presets** — one-click Precise / Balanced / Creative configurations
- **Markdown rendering** — user prompts and AI responses render with sanitized Markdown, including code blocks
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
├── makeaccount.py          # Create an account from the terminal
├── requirements.txt        # Python dependencies
├── users.json              # Account password hashes, created on first signup
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

After setup finishes, use the generated `launch_synapse.bat` / `launch_synapse.sh` to start Synapse from then on. Each person can create their own account from the login page.

> The shell and Python scripts automatically create a virtual environment (`.venv`) inside the project folder so nothing pollutes your global Python install.

---

## Manual setup

### 1. Clone the repo

```bash
git clone https://github.com/yourusername/synaps_ai.git
cd synaps_ai/synapse_ai
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
3. Keep the **Host** dropdown at `localhost` when LM Studio and Synapse run on the same computer. Only use `0.0.0.0` when Synapse is on a different trusted computer.
4. Leave the port at `1234` (default)

### 4. Run Synapse

Run the app:

```bash
python app.py
```

Open `http://localhost:6767`, create an account with a unique password of at least 12 characters, and share the address with other intended users. Anyone who can reach the login page can create an account, but accounts cannot read, rename, or delete another user's conversations. Passwords are stored as salted PBKDF2 hashes, not plaintext. The first account registration removes any pre-existing shared conversations from the old version.

Sign-in and account creation are separate pages (`/login` and `/register`). In the app, choose a color theme in **Settings → Appearance**; it is saved per browser.

In Settings, you can also choose message layout and font. Hover over one of your messages and choose **Edit** to revise it; later conversation turns are discarded and a new answer is generated. `Enter` sends a message, `Ctrl+Enter` regenerates the latest answer, and `Shift+Enter` inserts a line break. VRAM reporting uses the host's `nvidia-smi` or `rocm-smi` command-line utility; it displays `N/A` when neither tool can report GPU memory.

The composer supports Markdown. Select text and use `Ctrl+B` for bold, `Ctrl+I` for italic, `Ctrl+K` for a link, `Ctrl+Shift+C` for inline code, `Ctrl+Shift+L` for a bullet list, or `Ctrl+Shift+M` for a fenced code block. The formatting toolbar has the same actions.

To permanently delete an account, open **Settings → Delete Account**, enter the current password, and confirm. This also removes all conversations belonging to that account; the deletion cannot be undone.

If web signup fails, stop Synapse and run `python makeaccount.py` from the project directory. Follow the terminal prompts, then restart Synapse and sign in with that account. The script uses the same account format and password hashing as the app; stop the server first to avoid simultaneous account-file updates.

By default, Synapse listens only on this computer (`127.0.0.1:6767`). It creates a local `.synapse_secret_key` file on first run and reuses it across restarts so browser sessions remain valid. Keep this file private and do not delete it during normal operation. If you deploy multiple app workers, set `SYNAPSE_SECRET_KEY` to the same long random secret for all workers.

You should see output like:

```
 * Running on http://127.0.0.1:6767
```

### 5. Open the app

- **On your machine:** http://localhost:6767

To allow other devices on your private network, set `SYNAPSE_HOST=0.0.0.0` before starting. For PowerShell use `$env:SYNAPSE_HOST = "0.0.0.0"`; for macOS/Linux use `export SYNAPSE_HOST=0.0.0.0`. Then open `http://YOUR_LOCAL_IP:6767` on the other device. Only do this on a trusted network.

Do not expose this HTTP server directly to the public internet or use port forwarding without HTTPS. For remote access, put it behind a trusted HTTPS reverse proxy and set `SYNAPSE_COOKIE_SECURE=1` so the session cookie is only sent over HTTPS. Do not set `SYNAPSE_COOKIE_SECURE=1` when accessing Synapse over plain HTTP; the browser will omit the authenticated session cookie. Public sign-in and signup forms use short-lived signed CSRF tokens, but authenticated use still requires the browser to retain its session cookie. Open signup is intentional for a trusted group; anyone who can reach the server can register.

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

If port 6767 is already in use, set `SYNAPSE_PORT` before starting:

```powershell
$env:SYNAPSE_PORT = "6768"
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

- **Accounts and conversations** are stored in `users.json` and `conversations.json` in the project folder. Back up both; losing `users.json` prevents existing users from signing in.
- **Model nicknames** are per-browser and session-only — they reset on page refresh by design, so nothing sensitive gets stored.
- **First response slowness** is normal — LM Studio loads the model into RAM/VRAM on demand. Subsequent messages in the same session are much faster.
- **VRAM stats** use the host's `nvidia-smi` or `rocm-smi` command-line utility; they display as `N/A` if neither utility can report GPU memory.
- The app runs in production mode (`debug=False`). For any remote access, use HTTPS and set `SYNAPSE_COOKIE_SECURE=1`.

---

## Troubleshooting

**"Error loading models" in the dropdown**
LM Studio's server isn't running, or the model API isn't available at `localhost:1234`. If LM Studio runs on a different computer, configure its API host carefully on a trusted network.

**Works on my machine but not on other devices**
Set Synapse's `SYNAPSE_HOST` to `0.0.0.0` on a trusted local network and check that the firewall allows the configured Synapse port. For LM Studio, use `0.0.0.0` only if Synapse runs on a different machine; otherwise `localhost` is preferable.

**Sign-in or signup form says it is invalid or expired**
Reload the login page and try again. If it persists, restart Synapse so it loads the latest code. If you can sign in but get sent back to login, check that `SYNAPSE_COOKIE_SECURE` is unset for `http://` links; authenticated sessions require the browser to retain its cookie. If signup still fails, stop the app and create the account with `python makeaccount.py`.

**First message never responds / times out**
The model is still loading. Large models can take 30–60 seconds on first load. Wait and try again — subsequent messages will be fast.

**Desktop notifications not working**
On some Linux setups, `plyer` needs `notify-send` or a D-Bus notification daemon. On macOS, you may need to grant terminal notification permissions in System Settings. Notifications are cosmetic — the app works without them.

**Port conflict**
Change Synapse's port with the `SYNAPSE_PORT` environment variable.

---

## License

MIT — do whatever you want with it.
