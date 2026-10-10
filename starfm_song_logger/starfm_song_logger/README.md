# Star FM Song Logger (Windows terminal)

A no-subscription prototype for capturing a live internet radio stream continuously, sending rolling audio samples to ShazamIO, and logging repeated song matches. It runs only while you have started the command and can be stopped with `Ctrl+C`.

## Before you start

- Windows 10/11
- Python 3.12 x64 recommended for this Windows setup. Python 3.13 currently triggers a source build of `shazamio-core==1.1.2` because a matching CPython 3.13 Windows wheel is not available.
- FFmpeg installed and available on your PATH
- A direct audio stream URL from the radio station/player. A web page URL is not enough.
- Internet access

## 1. Install Python

Install Python 3.12 x64 from https://www.python.org/downloads/release/python-31210/ (or run `winget install --id Python.Python.3.12 -e`). You can keep Python 3.13 installed too. Confirm the launcher sees 3.12 with `py -3.12 --version`.

## 2. Install FFmpeg

One option is to open PowerShell or Command Prompt and run:

```bat
winget install Gyan.FFmpeg
```

Close and reopen the terminal, then test:

```bat
ffmpeg -version
```

If the command is not found, FFmpeg's `bin` folder needs to be added to PATH.

## 3. Install the Python dependency

Open Command Prompt in the folder containing these files, then run:

```bat
py -3.12 -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If you already created `.venv` with Python 3.13 and installation failed, remove that environment first from Command Prompt with `rmdir /s /q .venv`, then run the commands above. Do not install Rust for this setup; use Python 3.12 so pip can use the prebuilt Windows wheel.

## 4. Stream URL

Star FM 95.3 MP3 stream: `https://solid2.streamupsolutions.com/proxy/starfm953?mp=/;type=mp3&1791569729873`

To find the stream URL for the station you want to log tracks for:
1. Open the station in the browser
2. Enable Developer Tools & go to Network tab
3. Enable 'Preserve log' & reload the page
4. Find the 'media' Type URL.
5. Use the URL in the script instead of the preconfigured one and re-run `start.bat`

## 5. Start monitoring

Double-click `start.bat`, or run this from Command Prompt in the project folder:

```bat
.venv\Scripts\python.exe starfm_logger.py
```

To override the configured stream for troubleshooting, you can still provide `--url "DIRECT_STREAM_URL"` explicitly.

It connects once with FFmpeg and maintains a short rolling buffer in memory; it does **not** archive the full radio broadcast. Recognition samples are 12 seconds long by default, approximately every 12 seconds. Press `Ctrl+C` to stop whenever you choose.

The app writes:

- `playlist.csv` — spreadsheet-friendly history, including first detection, last confirmed detection, title, artist, recognition count and notes
- `playlist.txt` — easy-to-read list of confirmed detections
- `starfm_logger.log` — diagnostic output

The CSV and TXT are retained between runs; new entries are appended to the existing playlist.

## Optional settings

Use a less frequent recognition interval (reduces requests but may miss more brief tracks):

```bat
python starfm_logger.py --url "DIRECT_STREAM_URL" --interval 18
```

For a more permissive test with only one matching sample required (faster entries but more false positives):

```bat
python starfm_logger.py --url "DIRECT_STREAM_URL" --confirmations 1
```

Do not set a very short interval by default: ShazamIO is an unofficial client to a remote service, and excessive requests may fail or be rate-limited.

## Accuracy and cost caveats

- The software and local files have no license fee; ShazamIO is free to install and describes itself as a reverse-engineered Shazam API client. Its remote service is not an unlimited, guaranteed API. Availability, anti-abuse measures and future compatibility are outside this program's control.
- An unmatched sample may be an intro, instrumental section, obscure track, station speech, an ad, or audio trouble. The program does not assume every miss means an advertisement.
- Two consistent matches help reduce one-off false detections, at the cost of delaying detection and potentially missing short tracks.
- Shazam may still recognize a song under a station voiceover. This first version does not reliably separate speech layered over music, so perfect filtering of in-song ads/voiceovers is not guaranteed. Review questionable samples/results for a high-quality playlist.
- Track times are detection times, not exact broadcast start/end times.
- Run the logger only on streams you are permitted to access and respect the station's terms.
