# Star FM Song Logger V2 (Windows terminal)

**V2 default: ask ShazamIO to identify a 12-second audio sample approximately every 30 seconds.** Two matching detections are required by default before a new track is logged.

A no-subscription prototype for continuously capturing a live internet radio stream, sending selected rolling audio samples to ShazamIO, and logging repeated song matches. It runs only while started and can be stopped with `Ctrl+C`.

## What changed in V2

- Recognition interval defaults to **30 seconds** (instead of 12 seconds).
- The maximum gap between two matching candidate detections defaults to **90 seconds**, so ordinary request latency does not discard a candidate immediately.
- The Star FM stream URL remains hardcoded; no URL prompt is required.
- Keeps a short rolling audio buffer in memory; it does not save a full broadcast.

## Requirements

- Windows 10/11
- Python 3.12 x64 recommended for this dependency setup
- FFmpeg installed and available on PATH
- Internet access

## Setup (only if you haven't already set up the previous version)

Install Python 3.12 x64 from https://www.python.org/downloads/release/python-31210/ (or run `winget install --id Python.Python.3.12 -e`). You can keep Python 3.13 installed too.

Install FFmpeg, for example:

```bat
winget install Gyan.FFmpeg
```

From Command Prompt in this folder:

```bat
py -3.12 -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If you already have a working `.venv` from the previous package, keep it; you do not need to reinstall dependencies for V2.

## Start and stop

Double-click `start.bat`, or run:

```bat
.venv\Scripts\python.exe starfm_logger.py
```

The direct Star FM 95.3 stream is configured in the script:

`https://solid2.streamupsolutions.com/proxy/starfm953?mp=/;type=mp3&1791569729873`

Press `Ctrl+C` to stop. Playlist files remain on disk between runs.

## Files produced

- `playlist.csv` — spreadsheet-friendly history, including first detection, last confirmed detection, artist, title, recognition count, and notes.
- `playlist.txt` — readable list of confirmed detections.
- `starfm_logger.log` — diagnostics.

Files are saved beside the script. New entries are appended to the existing playlist; existing data is not intentionally deleted.

## Default behavior

- Audio sample length: **12 seconds**.
- Recognition interval: **30 seconds** (about two recognition requests per minute when calls complete normally).
- Confirmations needed before logging a new track: **2**.
- Maximum gap between matching candidate samples: **90 seconds**.

Optional overrides can be supplied from Command Prompt:

```bat
.venv\Scripts\python.exe starfm_logger.py --interval 30 --sample-seconds 12 --confirmations 2 --candidate-timeout 90
```

Do not set a very short interval by default: ShazamIO is an unofficial client to a remote service. It is free to install, but remote availability, anti-abuse measures, rate limits and future compatibility are not guaranteed.

## Accuracy and cost limitations

- The software and local files have no license fee. ShazamIO does not provide a guarantee of unlimited, uninterrupted access to Shazam's service.
- A sample with no match is not automatically assumed to be an advertisement: it could be an intro, instrumental section, obscure song, speech, or audio trouble.
- Two matching detections reduce one-off false positives but add delay and may miss short songs.
- Shazam can still recognize a song while a station voiceover or ad is layered over it. This version does not perfectly separate those elements.
- Times are detection times, not exact song start/end times.
- Use the logger only on streams you are permitted to access, and respect the station's terms.
