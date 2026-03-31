#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"
PLIST_NAME="com.amir.jarvis"
PLIST_SRC="$PROJECT_DIR/$PLIST_NAME.plist"
PLIST_DST="$HOME/Library/LaunchAgents/$PLIST_NAME.plist"
LOG_DIR="$HOME/Library/Logs/jarvis"

echo "==> Jarvis installer"
echo "    Project: $PROJECT_DIR"

# 1. Install portaudio via Homebrew (C library required by sounddevice)
if command -v brew &>/dev/null; then
    if ! brew list portaudio &>/dev/null; then
        echo "==> Installing portaudio via Homebrew..."
        brew install portaudio
    else
        echo "==> portaudio already installed"
    fi
else
    echo "ERROR: Homebrew not found. Install it from https://brew.sh then re-run this script."
    exit 1
fi

# 2. Create Python virtual environment
echo "==> Creating virtual environment at $VENV_DIR"
python3 -m venv "$VENV_DIR"

# 3. Install Python dependencies
echo "==> Installing Python dependencies"
"$VENV_DIR/bin/pip" install --upgrade pip --quiet
"$VENV_DIR/bin/pip" install -r "$PROJECT_DIR/requirements.txt" --quiet

# 4. Create log directory
mkdir -p "$LOG_DIR"

# 5. Install the LaunchAgent plist
echo "==> Installing LaunchAgent"
mkdir -p "$HOME/Library/LaunchAgents"
cp "$PLIST_SRC" "$PLIST_DST"

# 6. Load the agent (unload first in case a previous version is running)
launchctl unload "$PLIST_DST" 2>/dev/null || true
launchctl load "$PLIST_DST"

echo ""
echo "==> Jarvis is running in the background."
echo ""
echo "    Clap twice (within 0.8s) to open Claude."
echo ""
echo "    Logs:      tail -f $LOG_DIR/jarvis.log"
echo "    Stop:      launchctl unload $PLIST_DST"
echo "    Restart:   launchctl load $PLIST_DST"
echo "    Uninstall: launchctl unload $PLIST_DST && rm $PLIST_DST"
echo ""
echo "NOTE: macOS will prompt for microphone access the first time."
echo "      If the prompt doesn't appear, go to:"
echo "      System Settings > Privacy & Security > Microphone"
echo "      and enable access for Terminal (or whichever app runs launchd)."
