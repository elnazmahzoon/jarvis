# Jarvis

A macOS background daemon that listens for a double clap and opens the Claude app — inspired by Iron Man's AI assistant.

Clap twice → welcome sound plays + Claude opens instantly.

---

## How it works

Jarvis runs silently as a macOS [LaunchAgent](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html), starting automatically at login and restarting itself if it ever crashes.

It captures microphone input in 23ms chunks (1024 samples at 44.1kHz) and looks for the sharp amplitude spike that is the acoustic signature of a hand clap. Two spikes within a 0.15–0.80 second window trigger the action.

**Why it doesn't false-trigger on music or speech:**
Sustained sounds (TV, conversation, music) keep the audio energy high across many consecutive chunks. A clap is different — it comes from silence, spikes hard, then drops back immediately. Jarvis only registers a clap when the current chunk is loud *and* the previous chunk was quiet, making it robust to background noise.

**On double-clap detection:**
The two clap timestamps are held in a 2-element queue. If their gap is between 150ms and 800ms, the trigger fires. A 2-second cooldown then prevents re-triggering on echoes or a third clap. After the trigger, `afplay` (macOS built-in) plays `welcome.mp3` in parallel with `open -a Claude`, so the sound and the app open at the same time.

---

## Requirements

- macOS 10.14 or later
- Python 3.9+
- [Homebrew](https://brew.sh)
- The [Claude for Mac](https://claude.ai/download) desktop app

---

## Check your Python version

Before installing, verify you have Python 3.9 or later:

```bash
python3 --version
```

If the command is not found or the version is below 3.9, install Python via Homebrew:

```bash
brew install python
```

Then confirm:

```bash
python3 --version
# Python 3.x.x
```

---

## Installation

Clone or download this repository, then run:

```bash
bash jarvis.sh install
```

The installer will:

1. Install `portaudio` via Homebrew (the C audio library that `sounddevice` wraps)
2. Create a Python virtual environment at `.venv/`
3. Install Python dependencies (`sounddevice`, `numpy`)
4. Copy the LaunchAgent plist to `~/Library/LaunchAgents/`
5. Load the agent — Jarvis starts immediately and on every future login

**Microphone access:** macOS will show a permission prompt the first time. Grant it. If you miss the prompt, go to **System Settings → Privacy & Security → Microphone** and enable access for Terminal.

---

## Usage

```
bash jarvis.sh <command>
```

| Command | Description |
|---|---|
| `install` | First-time setup: install deps, register, and start |
| `start` | Load the LaunchAgent (start Jarvis) |
| `stop` | Unload the LaunchAgent (stop Jarvis) |
| `reload` | Restart Jarvis (stop + start) |
| `uninstall` | Stop Jarvis and remove all installed files |

---

## Welcome sound

Place an MP3 file named `welcome.mp3` in the project directory:

```
jarvis/
└── welcome.mp3   ← your audio file here
```

Jarvis plays it in parallel with opening Claude when a double clap is detected. If the file is missing, Jarvis skips the sound and still opens Claude.

---

## File structure

```
jarvis/
├── clap_detector.py        # Core script — audio capture and clap detection
├── com.amir.jarvis.plist   # macOS LaunchAgent descriptor
├── jarvis.sh               # CLI: install / start / stop / reload / uninstall
├── requirements.txt        # Python dependencies
└── welcome.mp3             # (optional) audio played on double clap
```

---

## Detection parameters

These constants are at the top of `clap_detector.py` and can be tuned to your environment.

| Constant | Default | Description |
|---|---|---|
| `RMS_THRESHOLD` | `0.15` | Minimum amplitude to register as a clap. Raise to `0.20` if you get false triggers; lower to `0.10` if claps are being missed. |
| `MIN_CLAP_GAP` | `0.15s` | Minimum time between two claps. Prevents a single clap's echo from counting as the second clap. |
| `MAX_CLAP_GAP` | `0.80s` | Maximum time between two claps. Increase to `1.0s` if you clap slowly. |
| `COOLDOWN` | `2.0s` | How long to ignore input after a trigger fires. Prevents a third clap or echo from re-opening Claude. |

After changing any parameter, reload Jarvis:

```bash
bash jarvis.sh reload
```

---

## Logs

All activity is written to `~/Library/Logs/jarvis/jarvis.log`.

```bash
# Watch live
tail -f ~/Library/Logs/jarvis/jarvis.log

# Check the last 50 lines
tail -n 50 ~/Library/Logs/jarvis/jarvis.log
```

Clap events are logged at `DEBUG` level, which is off by default. To enable them for troubleshooting, change `logging.INFO` to `logging.DEBUG` in `clap_detector.py` and reload.

---

## Troubleshooting

**Claude doesn't open after a double clap**
Check the log for errors. The most common cause is a missing microphone permission — verify it in System Settings → Privacy & Security → Microphone.

**Too many false triggers**
Raise `RMS_THRESHOLD` in `clap_detector.py` from `0.15` to `0.20` and reload.

**Claps are not being detected**
Lower `RMS_THRESHOLD` to `0.10`, or clap sharper and closer to the microphone.

**The welcome sound doesn't play**
Confirm `welcome.mp3` exists in the project directory and the filename is exact (case-sensitive).

**Jarvis isn't running after a reboot**
The LaunchAgent should start it automatically. If it doesn't, check:
```bash
launchctl list | grep jarvis
```
If it's not listed, run `bash jarvis.sh start`.

---

## Uninstall

```bash
bash jarvis.sh uninstall
```

This stops the daemon, removes the LaunchAgent plist from `~/Library/LaunchAgents/`, and deletes the `.venv/` directory. The project folder itself is left untouched.

---

## How the trigger pipeline works

```
Microphone
    │
    ▼  (23ms chunks via sounddevice callback)
RMS energy calculation
    │
    ▼  current_rms ≥ 0.15 AND prev_rms < 0.075?
Clap detected → timestamp pushed to deque[2]
    │
    ▼  two claps? gap between 0.15s and 0.80s?
Double clap confirmed
    │
    ├──▶  afplay welcome.mp3   (non-blocking)
    └──▶  open -a Claude       (non-blocking)
              │
              ▼
         2.0s cooldown
```
