#!/usr/bin/env python3
"""
Jarvis - Double-Clap Detector
Listens for two claps within a time window, plays welcome.mp3, then opens Claude.
"""

import queue
import subprocess
import sys
import time
import logging
import os
from collections import deque

import numpy as np
import sounddevice as sd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
WELCOME_SOUND = os.path.join(os.path.dirname(
    os.path.abspath(__file__)), "welcome.mp3")

# ---------------------------------------------------------------------------
# Detection parameters
# ---------------------------------------------------------------------------
SAMPLE_RATE = 44100   # Hz — standard mic rate
CHUNK_SIZE = 1024    # samples (~23ms per chunk) — catches clap's sharp attack
CHANNELS = 1       # mono

# float32 [0.0–1.0]; soft claps ~0.04–0.10, loud claps ~0.15–0.40, speech ~0.05–0.08
RMS_THRESHOLD = 0.03
ATTACK_RATIO = 1.8     # clap RMS must be >= ATTACK_RATIO × prev_rms (sharp spike)
MIN_CLAP_GAP = 0.08    # seconds — prevents clap echo being counted as 2nd clap
MAX_CLAP_GAP = 1.00    # seconds — natural double-clap window
COOLDOWN = 2.0     # seconds — suppresses re-trigger after a double clap

# ---------------------------------------------------------------------------
# Trigger queue — audio callback signals main thread; avoids spawning processes
# from inside the real-time PortAudio callback thread (which breaks afplay).
# ---------------------------------------------------------------------------
trigger_queue: queue.Queue = queue.Queue()

# ---------------------------------------------------------------------------
# State (audio callback only)
# ---------------------------------------------------------------------------
clap_times = deque(maxlen=2)  # timestamps of the last 2 detected claps
last_trigger = 0.0              # monotonic time of last double-clap trigger
prev_rms = 0.0              # RMS of the previous audio chunk


def compute_rms(chunk: np.ndarray) -> float:
    return float(np.sqrt(np.mean(chunk.astype(np.float32) ** 2)))


def audio_callback(indata, frames, time_info, status) -> None:
    global prev_rms, last_trigger

    if status:
        logging.warning("Audio stream status: %s", status)

    now = time.monotonic()
    rms = compute_rms(indata[:, 0])

    # Skip processing during cooldown period
    if now - last_trigger < COOLDOWN:
        prev_rms = rms
        return

    # A clap = current chunk is loud AND is a sharp spike relative to previous chunk.
    # The ratio check rejects sustained sounds (music, speech) which stay loud
    # across many chunks with no sudden jump.
    is_clap = rms >= RMS_THRESHOLD and (prev_rms < 0.001 or rms / prev_rms >= ATTACK_RATIO)

    if is_clap:
        clap_times.append(now)
        logging.debug("Clap at t=%.3f  RMS=%.4f  prev_RMS=%.4f",
                      now, rms, prev_rms)

        if len(clap_times) == 2:
            gap = clap_times[1] - clap_times[0]
            if MIN_CLAP_GAP <= gap <= MAX_CLAP_GAP:
                last_trigger = now
                clap_times.clear()
                trigger_queue.put_nowait("trigger")  # signal main thread
            elif gap > MAX_CLAP_GAP:
                # Gap too long — discard oldest, keep the newer clap
                clap_times.popleft()

    prev_rms = rms


def handle_trigger() -> None:
    """Called from the main thread — safe to spawn processes here."""
    logging.info(
        "Double clap detected — playing welcome sound and opening Claude")

    # Open Claude first, then play sound — both non-blocking so they overlap
    try:
        subprocess.Popen(
            ["osascript", "-e",
             'tell application "Claude" to activate',
             "-e", 'delay 0.5',
             "-e", 'tell application "System Events" to keystroke "n" using command down'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        logging.info("Launched: Claude with new chat")
    except Exception as exc:
        logging.error("open Claude failed: %s", exc)

    if os.path.isfile(WELCOME_SOUND):
        try:
            subprocess.Popen(
                ["afplay", WELCOME_SOUND],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            logging.info("Launched: afplay welcome.mp3")
        except Exception as exc:
            logging.error("afplay failed: %s", exc)
    else:
        logging.warning(
            "welcome.mp3 not found at %s — skipping audio", WELCOME_SOUND)


def main() -> None:
    log_dir = os.path.expanduser("~/Library/Logs/jarvis")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "jarvis.log")

    logging.basicConfig(
        filename=log_file,
        level=logging.DEBUG,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    logging.info("Jarvis starting — listening for double clap")
    logging.info(
        "Config: RMS_THRESHOLD=%.2f  ATTACK_RATIO=%.1f  MIN_GAP=%.2fs  MAX_GAP=%.2fs  COOLDOWN=%.1fs",
        RMS_THRESHOLD, ATTACK_RATIO, MIN_CLAP_GAP, MAX_CLAP_GAP, COOLDOWN,
    )

    try:
        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            blocksize=CHUNK_SIZE,
            channels=CHANNELS,
            dtype="float32",
            callback=audio_callback,
        ):
            logging.info("Audio stream open — ready")
            while True:
                try:
                    trigger_queue.get(timeout=1)
                    handle_trigger()
                except queue.Empty:
                    pass  # no trigger, keep listening
    except KeyboardInterrupt:
        logging.info("Stopped by user")
        sys.exit(0)
    except Exception as exc:
        logging.error("Fatal error: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
