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
WELCOME_SOUND = os.path.join(os.path.dirname(os.path.abspath(__file__)), "welcome.mp3")

# ---------------------------------------------------------------------------
# Detection parameters
# ---------------------------------------------------------------------------
SAMPLE_RATE    = 44100   # Hz — standard mic rate
CHUNK_SIZE     = 1024    # samples (~23ms per chunk) — catches clap's sharp attack
CHANNELS       = 1       # mono

RMS_THRESHOLD  = 0.15    # float32 [0.0–1.0]; claps hit ~0.15–0.40, speech ~0.05–0.08
MIN_CLAP_GAP   = 0.15    # seconds — prevents clap echo being counted as 2nd clap
MAX_CLAP_GAP   = 0.80    # seconds — natural double-clap window
COOLDOWN       = 2.0     # seconds — suppresses re-trigger after a double clap

# ---------------------------------------------------------------------------
# Trigger queue — audio callback signals main thread; avoids spawning processes
# from inside the real-time PortAudio callback thread (which breaks afplay).
# ---------------------------------------------------------------------------
trigger_queue: queue.Queue = queue.Queue()

# ---------------------------------------------------------------------------
# State (audio callback only)
# ---------------------------------------------------------------------------
clap_times   = deque(maxlen=2)  # timestamps of the last 2 detected claps
last_trigger = 0.0              # monotonic time of last double-clap trigger
prev_rms     = 0.0              # RMS of the previous audio chunk


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

    # A clap = current chunk is loud AND previous chunk was quiet (sharp attack).
    # This rejects sustained sounds (music, speech) which keep RMS high across
    # many consecutive chunks with no sudden quiet→loud transition.
    is_clap = rms >= RMS_THRESHOLD and prev_rms < RMS_THRESHOLD * 0.5

    if is_clap:
        clap_times.append(now)
        logging.debug("Clap at t=%.3f  RMS=%.4f  prev_RMS=%.4f", now, rms, prev_rms)

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
    logging.info("Double clap detected — playing welcome sound and opening Claude")

    if os.path.isfile(WELCOME_SOUND):
        # Wait for afplay to finish so the sound plays before Claude comes to front
        subprocess.run(
            ["afplay", WELCOME_SOUND],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        logging.warning("welcome.mp3 not found at %s — skipping audio", WELCOME_SOUND)

    subprocess.Popen(
        ["open", "-a", "Claude"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def main() -> None:
    log_dir = os.path.expanduser("~/Library/Logs/jarvis")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "jarvis.log")

    logging.basicConfig(
        filename=log_file,
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    logging.info("Jarvis starting — listening for double clap")
    logging.info(
        "Config: RMS_THRESHOLD=%.2f  MIN_GAP=%.2fs  MAX_GAP=%.2fs  COOLDOWN=%.1fs",
        RMS_THRESHOLD, MIN_CLAP_GAP, MAX_CLAP_GAP, COOLDOWN,
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
