#!/usr/bin/env python3
"""Star FM Song Logger V2: continuous local capture + periodic ShazamIO recognition.

Python 3.10+. Requires FFmpeg on PATH and the free shazamio Python package.
Run: python starfm_logger.py --url "DIRECT_AUDIO_STREAM_URL"
Stop with Ctrl+C. Writes playlist.csv, playlist.txt and starfm_logger.log beside this file.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import io
import logging
import shutil
import subprocess
import sys
import threading
import time
import uuid
import wave
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any

from shazamio import Shazam

ROOT = Path(__file__).resolve().parent
# Verified Star FM 95.3 direct Shoutcast/MP3 endpoint.
DEFAULT_STREAM_URL = "https://solid2.streamupsolutions.com/proxy/starfm953?mp=/;type=mp3&1791569729873"
CSV_FILE = ROOT / "playlist.csv"
TXT_FILE = ROOT / "playlist.txt"
LOG_FILE = ROOT / "starfm_logger.log"
SAMPLE_RATE = 16_000
SAMPLE_WIDTH = 2  # signed 16-bit PCM
CHANNELS = 1
BYTES_PER_SECOND = SAMPLE_RATE * SAMPLE_WIDTH * CHANNELS
CSV_FIELDS = [
    "session_id", "track_entry_id", "first_detected_local", "last_confirmed_local",
    "artist", "title", "shazam_track_id", "recognition_count", "status", "notes",
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler(LOG_FILE, encoding="utf-8")],
)
logger = logging.getLogger("starfm_logger")


def now_local() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def ensure_outputs() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if CSV_FILE.exists() and CSV_FILE.stat().st_size:
        try:
            with CSV_FILE.open("r", newline="", encoding="utf-8-sig") as f:
                for row in csv.DictReader(f):
                    rows.append({k: str(row.get(k, "") or "") for k in CSV_FIELDS})
        except (OSError, csv.Error) as exc:
            logger.warning("Could not read prior CSV; starting a new playlist file: %s", exc)
            rows = []
    write_csv(rows)
    if not TXT_FILE.exists():
        TXT_FILE.write_text("Star FM Song Logger — confirmed track detections\n", encoding="utf-8")
    return rows


def write_csv(rows: list[dict[str, str]]) -> None:
    temp = CSV_FILE.with_suffix(".csv.tmp")
    with temp.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    temp.replace(CSV_FILE)


def wav_bytes(pcm: bytes) -> bytes:
    buff = io.BytesIO()
    with wave.open(buff, "wb") as wav:
        wav.setnchannels(CHANNELS)
        wav.setsampwidth(SAMPLE_WIDTH)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(pcm)
    return buff.getvalue()


class LiveAudioCapture:
    """Keeps a single FFmpeg connection open and stores only a rolling audio buffer."""
    def __init__(self, url: str, sample_seconds: int):
        self.url = url
        self.sample_bytes = sample_seconds * BYTES_PER_SECOND
        # Retain a little more than the required window, but never the full broadcast.
        self.max_buffer_bytes = (sample_seconds + 3) * BYTES_PER_SECOND
        self._buffer = bytearray()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._proc: subprocess.Popen[bytes] | None = None
        self._ever_received_audio = False

    def start(self) -> None:
        if not shutil.which("ffmpeg"):
            raise RuntimeError(
                "FFmpeg was not found. Install it, add ffmpeg.exe to PATH, then reopen the terminal."
            )
        self._thread = threading.Thread(target=self._reader, name="radio-audio-reader", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        proc = self._proc
        if proc and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        if self._thread:
            self._thread.join(timeout=4)

    def ready(self) -> bool:
        with self._lock:
            return len(self._buffer) >= self.sample_bytes

    def seconds_buffered(self) -> float:
        with self._lock:
            return len(self._buffer) / BYTES_PER_SECOND

    def snapshot_wav(self) -> bytes | None:
        with self._lock:
            if len(self._buffer) < self.sample_bytes:
                return None
            raw = bytes(self._buffer[-self.sample_bytes:])
        return wav_bytes(raw)

    @staticmethod
    def _drain_stderr(pipe, tail: deque[str]) -> None:
        """Drain FFmpeg stderr so diagnostics are retained without blocking FFmpeg."""
        if pipe is None:
            return
        try:
            for raw_line in iter(pipe.readline, b""):
                line = raw_line.decode("utf-8", errors="replace").strip()
                if line:
                    tail.append(line)
        except Exception:
            pass

    def _reader(self) -> None:
        chunk_bytes = BYTES_PER_SECOND // 2  # target roughly 0.5 second per read
        while not self._stop.is_set():
            # Keep these arguments close to the simple FFmpeg command already tested
            # against the stream. The outer loop performs reconnects after EOF/errors.
            cmd = [
                "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
                "-i", self.url,
                "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE),
                "-f", "s16le", "pipe:1",
            ]
            proc = None
            stderr_tail: deque[str] = deque(maxlen=12)
            stderr_thread = None
            stream_ended = False
            try:
                proc = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0
                )
                self._proc = proc
                stderr_thread = threading.Thread(
                    target=self._drain_stderr, args=(proc.stderr, stderr_tail),
                    name="ffmpeg-stderr-reader", daemon=True,
                )
                stderr_thread.start()
                logger.info("Connecting to the live audio stream...")
                assert proc.stdout is not None
                while not self._stop.is_set():
                    data = proc.stdout.read(chunk_bytes)
                    if not data:
                        stream_ended = True
                        break
                    with self._lock:
                        self._buffer.extend(data)
                        overflow = len(self._buffer) - self.max_buffer_bytes
                        if overflow > 0:
                            del self._buffer[:overflow]
                    if not self._ever_received_audio:
                        self._ever_received_audio = True
                        logger.info("Audio received; filling the initial sample buffer.")
            except Exception as exc:
                if not self._stop.is_set():
                    logger.warning("Audio capture error: %s", exc)
            finally:
                if proc is not None:
                    try:
                        if proc.poll() is None and self._stop.is_set():
                            proc.terminate()
                        if proc.poll() is None and stream_ended:
                            # The child closed stdout but may still be flushing diagnostics.
                            proc.wait(timeout=2)
                        elif proc.poll() is None and not self._stop.is_set():
                            # On an unexpected reader error, force a clean restart.
                            proc.terminate()
                            proc.wait(timeout=2)
                    except Exception:
                        try:
                            proc.kill()
                            proc.wait(timeout=2)
                        except Exception:
                            pass
                    if stderr_thread:
                        stderr_thread.join(timeout=1)
                    rc = proc.poll()
                    detail = " | ".join(stderr_tail)
                    if stream_ended and not self._stop.is_set():
                        if not detail:
                            detail = "FFmpeg closed its audio output without an error message."
                        logger.warning(
                            "Audio stream ended (FFmpeg exit code %s): %s. Reconnecting in 3 seconds.",
                            rc, detail,
                        )
                    self._proc = None
            if not self._stop.is_set():
                self._stop.wait(3)


def parse_track(result: Any) -> tuple[str, str, str] | None:
    """Handle ShazamIO's common response shape without treating empty results as songs."""
    if not isinstance(result, dict):
        return None
    track = result.get("track")
    if not isinstance(track, dict):
        return None
    title = str(track.get("title") or "").strip()
    artist = str(track.get("subtitle") or "").strip()
    track_id = str(track.get("key") or track.get("trackId") or "").strip()
    if not title or not artist:
        return None
    return artist, title, track_id


async def identify(shazam: Shazam, audio: bytes) -> tuple[str, str, str] | None:
    try:
        result = await shazam.recognize(audio)
        return parse_track(result)
    except Exception as exc:
        logger.warning("ShazamIO recognition request failed: %s", exc)
        return None


def append_text_entry(when: str, artist: str, title: str) -> None:
    with TXT_FILE.open("a", encoding="utf-8") as f:
        f.write(f"{when} | {artist} - {title}\n")


async def monitor(args: argparse.Namespace) -> None:
    rows = ensure_outputs()
    run_id = str(uuid.uuid4())
    capture = LiveAudioCapture(args.url, args.sample_seconds)
    capture.start()
    logger.info("Monitoring started. Press Ctrl+C to stop.")
    logger.info("Using Star FM stream URL: %s", args.url)
    logger.info("Results: %s", CSV_FILE)
    logger.info("Text list: %s", TXT_FILE)
    logger.info(
        "V2 | audio window: %ss | recognition start interval: %ss | confirmations: %s | candidate timeout: %ss",
        args.sample_seconds, args.interval, args.confirmations, args.candidate_timeout,
    )
    logger.info("No full broadcast is saved; only the rolling in-memory buffer is retained.")

    current_key: str | None = None
    current_row_id: str | None = None
    candidate_key: str | None = None
    candidate_artist = ""
    candidate_title = ""
    candidate_track_id = ""
    candidate_when = ""
    candidate_hits = 0
    candidate_last_seen = 0.0
    misses_since_last_match = 0
    next_check = time.monotonic()

    try:
        # ShazamIO 0.8.1 does not implement async context-manager methods.
        # Its HTTP client creates and closes a session per request, so instantiate directly.
        shazam = Shazam()
        # Wait for a full window so recognition never gets an incomplete initial sample.
        while not capture.ready():
            if capture._stop.is_set():
                return
            await asyncio.sleep(0.25)
        logger.info("Initial buffer ready; recognition is beginning.")

        while True:
            delay = next_check - time.monotonic()
            if delay > 0:
                await asyncio.sleep(delay)
            sample = capture.snapshot_wav()
            sampled_at = now_local()
            if sample is None:
                logger.info("Waiting for enough audio to fill the next sample.")
            else:
                match = await identify(shazam, sample)
                now_mono = time.monotonic()

                if match is None:
                    misses_since_last_match += 1
                    logger.info("No song match for this sample; this is not proof it was an ad.")
                else:
                    unmatched_before_match = misses_since_last_match
                    artist, title, track_id = match
                    key = track_id or f"{artist.casefold()}|{title.casefold()}"
                    logger.info("Matched: %s - %s", artist, title)
                    misses_since_last_match = 0

                    if key == current_key and current_row_id:
                        for row in reversed(rows):
                            if row["track_entry_id"] == current_row_id:
                                row["last_confirmed_local"] = sampled_at
                                try:
                                    row["recognition_count"] = str(int(row["recognition_count"]) + 1)
                                except ValueError:
                                    row["recognition_count"] = "1"
                                if not row["shazam_track_id"]:
                                    row["shazam_track_id"] = track_id
                                if unmatched_before_match:
                                    gap_note = f"{unmatched_before_match} unmatched sample(s) between matches; interruption is unverified"
                                    if gap_note not in row["notes"]:
                                        row["notes"] = (row["notes"] + " " + gap_note).strip()
                                break
                        write_csv(rows)
                        candidate_key = None
                        candidate_hits = 0
                    else:
                        # A different result must recur before it is entered in the playlist.
                        if key == candidate_key and now_mono - candidate_last_seen <= args.candidate_timeout:
                            candidate_hits += 1
                        else:
                            candidate_key = key
                            candidate_artist = artist
                            candidate_title = title
                            candidate_track_id = track_id
                            candidate_when = sampled_at
                            candidate_hits = 1
                        candidate_last_seen = now_mono

                        if candidate_hits >= args.confirmations:
                            entry_id = str(uuid.uuid4())
                            notes = "Repeated ShazamIO match; song start/end are approximate detection times."
                            new_row = {
                                "session_id": run_id,
                                "track_entry_id": entry_id,
                                "first_detected_local": candidate_when,
                                "last_confirmed_local": sampled_at,
                                "artist": candidate_artist,
                                "title": candidate_title,
                                "shazam_track_id": candidate_track_id,
                                "recognition_count": str(candidate_hits),
                                "status": "CONFIRMED_MATCH",
                                "notes": notes,
                            }
                            rows.append(new_row)
                            write_csv(rows)
                            append_text_entry(candidate_when, candidate_artist, candidate_title)
                            logger.info("LOGGED: %s - %s", candidate_artist, candidate_title)
                            current_key = candidate_key
                            current_row_id = entry_id
                            candidate_key = None
                            candidate_hits = 0

            # Keep sample windows on a regular cadence. If an API call runs long,
            # skip missed ticks rather than firing a burst of catch-up requests.
            next_check += args.interval
            now = time.monotonic()
            if next_check <= now:
                next_check = now + args.interval
    finally:
        capture.stop()
        logger.info("Monitoring stopped. Playlist files are saved.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Continuously capture a live radio stream and log repeated ShazamIO song matches."
    )
    parser.add_argument("--url", default=DEFAULT_STREAM_URL,
                        help="Direct audio-stream URL (defaults to the hardcoded Star FM 95.3 stream).")
    parser.add_argument("--sample-seconds", type=int, default=12,
                        help="Seconds in each recognition sample (default: 12; allowed 6–12).")
    parser.add_argument("--interval", type=int, default=30,
                        help="Seconds between recognition attempts, approximately (default: 30).")
    parser.add_argument("--confirmations", type=int, default=2,
                        help="Repeated same-track matches needed before logging (default: 2).")
    parser.add_argument("--candidate-timeout", type=int, default=90,
                        help="Maximum seconds between matching candidate samples (default: 90).")
    args = parser.parse_args()
    # Trim pasted/configured whitespace: FFmpeg treats leading spaces as part of the URL.
    args.url = (args.url or DEFAULT_STREAM_URL).strip()
    if not args.url:
        parser.error("The stream URL cannot be empty.")
    if not 6 <= args.sample_seconds <= 12:
        parser.error("--sample-seconds must be between 6 and 12; Shazam signatures cover up to about 12 seconds.")
    if args.interval < 8:
        parser.error("--interval must be at least 8 seconds to avoid excessively frequent requests.")
    if args.confirmations < 1:
        parser.error("--confirmations must be at least 1.")
    if args.candidate_timeout < args.interval:
        parser.error("--candidate-timeout must be at least --interval.")
    return args


def main() -> None:
    args = parse_args()
    try:
        asyncio.run(monitor(args))
    except KeyboardInterrupt:
        # asyncio cancellation triggers monitor's finally block to stop FFmpeg.
        print("\nStopped. Check playlist.csv and playlist.txt.")
    except Exception as exc:
        logger.exception("Fatal error: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
