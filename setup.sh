#!/usr/bin/env bash
set -e

# ── Colors ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

# ── Banner ────────────────────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}${BOLD} =========================================="
echo -e "   Synapse AI — One-Click Setup"
echo -e " ==========================================${RESET}"
echo ""

# ── Helper functions ──────────────────────────────────────────────────────────
step() { echo -e "${CYAN}[${1}/5]${RESET} ${BOLD}${2}${RESET}"; }
ok()   { echo -e "  ${GREEN}✓${RESET} ${1}"; }
warn() { echo -e "  ${YELLOW}⚠${RESET}  ${1}"; }
die()  {
    echo ""
    echo -e "  ${RED}✗ ERROR:${RESET} ${1}"
    echo ""
    exit 1
}

# ── 1. Check Python ───────────────────────────────────────────────────────────
step 1 "Checking for Python 3..."

PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        VER=$("$cmd" -c 'import sys; print(sys.version_info[:2])' 2>/dev/null)
        MAJOR=$("$cmd" -c 'import sys; print(sys.version_info[0])')
        MINOR=$("$cmd" -c 'import sys; print(sys.version_info[1])')
        if [ "$MAJOR" -ge 3 ] && [ "$MINOR" -ge 8 ]; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    die "Python 3.8+ not found.\n  Install it from https://www.python.org/downloads/\n  or via your package manager (brew install python3 / sudo apt install python3)"
fi

ok "Found $($PYTHON --version)"

# ── 2. Check Git ──────────────────────────────────────────────────────────────
step 2 "Checking for Git..."

if ! command -v git &>/dev/null; then
    die "Git not found.\n  Mac:   brew install git\n  Linux: sudo apt install git  (or equivalent)"
fi

ok "Found $(git --version)"

# ── 3. Clone repo ─────────────────────────────────────────────────────────────
step 3 "Cloning Synapse AI repository..."

if [ -d "synapse_ai" ]; then
    warn "Folder 'synapse_ai' already exists — skipping clone."
    warn "Delete it and re-run for a fresh install."
else
    git clone https://github.com/MrCryptographic/synapse_ai.git \
        || die "Failed to clone repository. Check your internet connection."
    ok "Cloned successfully."
fi

# ── 4. Install dependencies ───────────────────────────────────────────────────
step 4 "Installing Python dependencies..."

cd synapse_ai

# Prefer a venv if we can, fall back to --break-system-packages
if $PYTHON -m venv --help &>/dev/null; then
    if [ ! -d ".venv" ]; then
        $PYTHON -m venv .venv
        ok "Created virtual environment (.venv)"
    else
        warn "Virtual environment already exists — reusing it."
    fi

    # Activate
    source .venv/bin/activate
    PYTHON="python"  # now points to venv python
fi

$PYTHON -m pip install --upgrade pip --quiet
$PYTHON -m pip install -r requirements.txt \
    || die "Failed to install dependencies. Try running:\n  pip install -r requirements.txt"

ok "Dependencies installed."
cd ..

# ── 5. Create launch script ───────────────────────────────────────────────────
step 5 "Creating launch script..."

cat > launch_synapse.sh << 'LAUNCHER'
#!/usr/bin/env bash
cd "$(dirname "$0")/synapse_ai"

# Activate venv if it exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

echo ""
echo " Starting Synapse AI..."
echo " Local:   http://localhost:6767"
echo " Create an individual account on first visit."
echo " Press Ctrl+C to stop."
echo ""

python app.py
LAUNCHER

chmod +x launch_synapse.sh
ok "Created launch_synapse.sh"

# ── Done ──────────────────────────────────────────────────────────────────────

echo ""
echo -e "${CYAN}${BOLD} =========================================="
echo -e "   Setup complete!"
echo -e " ==========================================${RESET}"
echo ""
echo -e " ${BOLD}Before launching, make sure LM Studio is:${RESET}"
echo "   1. Open with the Local Server running"
echo "   2. Host set to localhost if LM Studio runs on this computer"
echo "   3. Port set to 1234  (default)"
echo ""
echo -e " ${BOLD}To start Synapse:${RESET}"
echo "   ./launch_synapse.sh"
echo ""
echo -e " ${BOLD}Then open:${RESET}"
echo "   Local:   http://localhost:6767"
echo "   Network access is disabled by default; see README.md before enabling it."
echo ""