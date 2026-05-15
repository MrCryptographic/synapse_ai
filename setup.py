#!/usr/bin/env python3
"""
Synapse AI — Universal Setup Script
Run with:  python setup.py
Works on Windows, macOS, and Linux.
"""

import sys
import os
import subprocess
import platform
import shutil
import textwrap

# ── Colours (disabled on Windows unless ANSICON/WT) ───────────────────────────
USE_COLOR = sys.stdout.isatty() and platform.system() != "Windows"

def c(text, code):
    return f"\033[{code}m{text}\033[0m" if USE_COLOR else text

def bold(t):   return c(t, "1")
def cyan(t):   return c(t, "36")
def green(t):  return c(t, "32")
def yellow(t): return c(t, "33")
def red(t):    return c(t, "31")

# ── Helpers ───────────────────────────────────────────────────────────────────
def banner(msg):
    bar = "=" * 44
    print(f"\n{cyan(bold(f' {bar}'))}")
    print(f"{cyan(bold(f'   {msg}'))}")
    print(f"{cyan(bold(f' {bar}'))}\n")

def step(n, msg):
    print(f"{cyan(f'[{n}/5]')} {bold(msg)}")

def ok(msg):
    print(f"  {green('✓')} {msg}")

def warn(msg):
    print(f"  {yellow('⚠')}  {msg}")

def die(msg):
    print(f"\n  {red('✗ ERROR:')} {msg}\n")
    sys.exit(1)

def run(cmd, **kwargs):
    """Run a command, raise on failure."""
    return subprocess.run(cmd, check=True, **kwargs)

def run_output(cmd):
    """Run a command and return stdout."""
    return subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode().strip()

# ── 1. Python version check ───────────────────────────────────────────────────
banner("Synapse AI — One-Click Setup")

step(1, "Checking Python version...")
major, minor = sys.version_info[:2]
if major < 3 or minor < 8:
    die(
        f"Python 3.8+ required. You have {major}.{minor}.\n"
        "  Download from: https://www.python.org/downloads/"
    )
ok(f"Python {major}.{minor} — good to go.")

# ── 2. Git check ──────────────────────────────────────────────────────────────
step(2, "Checking for Git...")
if not shutil.which("git"):
    die(
        "Git not found.\n"
        "  Windows: https://git-scm.com/download/win\n"
        "  Mac:     brew install git\n"
        "  Linux:   sudo apt install git"
    )
try:
    git_ver = run_output(["git", "--version"])
    ok(git_ver)
except Exception:
    die("Git found but could not get version. Make sure it's properly installed.")

# ── 3. Clone ──────────────────────────────────────────────────────────────────
step(3, "Cloning Synapse AI repository...")

REPO_URL  = "https://github.com/MrCryptographic/synapse_ai.git"
REPO_DIR  = "synapse_ai"

if os.path.isdir(REPO_DIR):
    warn(f"Folder '{REPO_DIR}' already exists — skipping clone.")
    warn("Delete it and re-run for a fresh install.")
else:
    try:
        run(["git", "clone", REPO_URL])
        ok("Repository cloned.")
    except subprocess.CalledProcessError:
        die("Failed to clone. Check your internet connection and try again.")

# ── 4. Install dependencies ───────────────────────────────────────────────────
step(4, "Installing Python dependencies...")

project_dir = os.path.abspath(REPO_DIR)
req_file    = os.path.join(project_dir, "requirements.txt")

if not os.path.isfile(req_file):
    die(f"requirements.txt not found at {req_file}. The clone may be incomplete.")

# Try to create a venv
venv_dir  = os.path.join(project_dir, ".venv")
venv_ok   = False

try:
    import venv as _venv  # noqa — just checking it's available
    if not os.path.isdir(venv_dir):
        run([sys.executable, "-m", "venv", venv_dir])
        ok("Virtual environment created (.venv)")
    else:
        warn("Virtual environment already exists — reusing.")
    venv_ok = True
except Exception:
    warn("Could not create virtual environment — installing into system Python.")

if venv_ok:
    if platform.system() == "Windows":
        pip_exe = os.path.join(venv_dir, "Scripts", "pip.exe")
    else:
        pip_exe = os.path.join(venv_dir, "bin", "pip")
else:
    pip_exe = shutil.which("pip3") or shutil.which("pip") or sys.executable + " -m pip"
    pip_exe = None  # fall through to module call below

try:
    if pip_exe and os.path.isfile(pip_exe):
        run([pip_exe, "install", "--upgrade", "pip", "--quiet"])
        run([pip_exe, "install", "-r", req_file])
    else:
        run([sys.executable, "-m", "pip", "install", "--upgrade", "pip", "--quiet"])
        run([sys.executable, "-m", "pip", "install", "-r", req_file])
    ok("Dependencies installed.")
except subprocess.CalledProcessError:
    die(
        "Failed to install dependencies.\n"
        f"  Try manually: pip install -r {req_file}"
    )

# ── 5. Create platform-specific launcher ─────────────────────────────────────
step(5, "Creating launch script...")

IS_WINDOWS = platform.system() == "Windows"

if IS_WINDOWS:
    launcher_path = "launch_synapse.bat"
    if venv_ok:
        activate = r'call synapse_ai\.venv\Scripts\activate.bat'
        python_cmd = "python"
    else:
        activate = ""
        python_cmd = "python"

    content = textwrap.dedent(f"""\
        @echo off
        title Synapse AI
        cd /d "%~dp0synapse_ai"
        {activate}
        echo.
        echo  Starting Synapse AI...
        echo  Open your browser at: http://localhost:5000
        echo  Press Ctrl+C to stop.
        echo.
        {python_cmd} app.py
        pause
    """)
    with open(launcher_path, "w") as f:
        f.write(content)
    ok(f"Created {launcher_path} — double-click it to start Synapse.")

else:
    launcher_path = "launch_synapse.sh"
    if venv_ok:
        activate_line = 'source "$(dirname "$0")/synapse_ai/.venv/bin/activate"'
    else:
        activate_line = "# no venv"

    content = textwrap.dedent(f"""\
        #!/usr/bin/env bash
        cd "$(dirname "$0")/synapse_ai"
        {activate_line}

        if command -v ipconfig &>/dev/null; then
            LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "your-local-ip")
        elif command -v hostname &>/dev/null; then
            LOCAL_IP=$(hostname -I 2>/dev/null | awk '{{print $1}}' || echo "your-local-ip")
        else
            LOCAL_IP="your-local-ip"
        fi

        echo ""
        echo " Starting Synapse AI..."
        echo " Local:   http://localhost:5000"
        echo " Network: http://${{LOCAL_IP}}:5000"
        echo " Press Ctrl+C to stop."
        echo ""
        python3 app.py
    """)
    with open(launcher_path, "w") as f:
        f.write(content)
    os.chmod(launcher_path, 0o755)
    ok(f"Created {launcher_path} — run it with: ./launch_synapse.sh")

# ── Done ──────────────────────────────────────────────────────────────────────
banner("Setup complete!")

print(f"  {bold('Before launching, make sure LM Studio is:')}")
print("    1. Open with the Local Server tab running")
print("    2. Host set to  0.0.0.0  (not localhost!)")
print("    3. Port set to  1234  (default)\n")

if IS_WINDOWS:
    print(f"  {bold('To start:')}  double-click  launch_synapse.bat\n")
else:
    print(f"  {bold('To start:')}  ./launch_synapse.sh\n")

print(f"  {bold('Then open:')}  http://localhost:5000")
print( "  Share your local IP with others on the same Wi-Fi.\n")