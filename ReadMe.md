# ABOUT THIS PROJECT

## Purpose

A small Python tool that can monitor radio stations and automatically build a playlist of the songs it recognizes.

Tested and found working for the greek station STAR FM 95.3

## How it works

* Connects to the radio's live MP3 stream.
* Continuously captures audio in memory and periodically sends short samples to **ShazamIO** for song recognition.
* Requires repeated matching detections before logging a new song, reducing false positives.
* Saves recognized songs and timestamps to `playlist.csv` and `playlist.txt`.
* Writes diagnostics and errors to `starfm_logger.log`.
* Does not save the entire radio broadcast.

## Versions

| Setting              | V1                             | V2         |
| -------------------- | ------------------------------ | ---------- |
| Audio sample         | 12 seconds                     | 12 seconds |
| Recognition interval | 12 seconds                     | 30 seconds |
| Confirmations to log | 2                              | 2          |
| Candidate timeout    | Version-dependent              | 90 seconds |
| Stream URL           | Hardcoded in the latest V1 fix | Hardcoded  |

**V1:** Checks more frequently, potentially recognizing more songs but making more requests to ShazamIO.

**V2:** Checks every 30 seconds to reduce recognition requests. Songs may take longer to confirm, and some songs may be missed.

## How to run

1. Open the project folder in Windows.
2. Run `start.bat`.
3. Leave it running while monitoring the station.
4. Press `Ctrl+C` to stop. Playlist files are saved locally.

## Requirements

* Windows
* Python 3.12 and the project's virtual environment (`.venv`)
* FFmpeg
* ShazamIO and an internet connection

## Important limitations

* ShazamIO is unofficial; its service availability and request limits are not guaranteed.
* Recognition is not perfect. Short songs, intros, voiceovers and advertisements may cause missed or incorrect matches.
* The tool does not reliably detect or remove every advertisement or station voiceover.
* The project has no paid subscription or API requirement, but it depends on an external recognition service.

## Output files

* `playlist.csv` — playlist suitable for Excel.
* `playlist.txt` — readable song list.
* `starfm_logger.log` — troubleshooting information.

