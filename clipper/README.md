# Clipper: The Gist Room

Daily, hands-off clipping for Whop Content Rewards campaigns. Runs on your laptop once a
day, picks the most viral moments from campaign footage with Claude Code (your Pro login,
no API key), renders 9:16 clips with burned-in captions, and schedules them through Post
for Me to your allowlisted accounts only.

```
campaigns.yaml ─► audio-only download ─► faster-whisper (word timestamps, cached)
      │                                          │
      │                    claude -p picks moments (JSON) ─► code checks: length, overlap,
      │                                                       score ≥ 7, banned words, required text
      ▼                                          │
Whop feed ─► "worth joining" list     download ONLY the clip section ─► ffmpeg 1080x1920
                                                 │                      captions + hook + loudnorm
                                                 ▼
                         Post for Me upload ─► scheduled posts (08:15 / 12:15 / 17:15 Lagos)
                                                 │      allowlist guard + external_id dedupe
                                                 ▼
                         next run: collect URLs ─► report with links to submit on Whop
```

## Disk and laptop load

| What | Size | When |
|---|---|---|
| Python packages + ffmpeg | ~1 GB | one-time |
| Whisper `small` model | ~0.5 GB | one-time, first run |
| Audio of one episode | ~50–60 MB per hour | deleted right after transcription |
| One clip section + render | ~20–60 MB | deleted right after upload |
| Transcripts | ~2–3 MB per hour of footage | auto-deleted after 45 days |

Full videos are never downloaded. The run refuses to start if less than 5 GB is free
(`CLIPPER_MIN_FREE_GB`). Transcription is CPU-heavy while it runs; that's the only part
you'll notice (fan noise). Each episode is transcribed once, ever.

## One-time setup (about 20 minutes)

**1. Install the tools.**

Windows (PowerShell):
```powershell
winget install Python.Python.3.12 Gyan.FFmpeg Git.Git
```
Mac (Terminal, with Homebrew):
```bash
brew install python@3.12 ffmpeg git
```
Close and reopen the terminal afterwards so the new commands are on PATH.

Claude Code must work from the terminal: run `claude --version`. If that fails, install the
Claude Code CLI from code.claude.com/docs and log in once by running `claude`.

**2. Get the code and install dependencies.**

Windows:
```powershell
cd $HOME
git clone -b claude/stoic-bell-1uj0ic https://github.com/Chi-Automates/clipster-reconciliation.git clipper-app
cd clipper-app
py -3.12 -m venv .venv
.\.venv\Scripts\pip install -r clipper\requirements.txt
```
Mac:
```bash
cd ~
git clone -b claude/stoic-bell-1uj0ic https://github.com/Chi-Automates/clipster-reconciliation.git clipper-app
cd clipper-app
python3.12 -m venv .venv
./.venv/bin/pip install -r clipper/requirements.txt
```

**3. Create `.env` in the `clipper-app` folder** (it is gitignored, never committed):
```
POSTFORME_API_KEY=your_post_for_me_key
POSTFORME_ALLOWED_ACCOUNT_IDS=spc_wIqUO4Qb4j9JSQDhihGX1,spc_xBwJnwAS3B90001AgKQhR,spc_X4X8E7B4K4PbyuoSnQYr
```
Those three IDs are YouTube (UCOT05AoW-Pm3hiFD7APYd1w), Instagram _thegistroom and X
ChiawalamJ65161. Nothing else can ever be posted to.

**4. Check, then dry-run.** (Windows: replace `./.venv/bin/python` with `.\.venv\Scripts\python`.)
```bash
./.venv/bin/python -m clipper check          # shows which accounts it will post to
./.venv/bin/python -m clipper daily --dry-run # everything except upload/publish
```
The dry run's renders are listed at the end of the report. Watch two of them.

**5. Schedule it.**

Windows (PowerShell):
```powershell
powershell -ExecutionPolicy Bypass -File clipper\scripts\install_windows_task.ps1
```
Runs daily at 07:00 Lagos time; if the laptop was off, it runs as soon as you log in.

Mac:
```bash
bash clipper/scripts/install_mac_launchd.sh
```
Runs daily at 07:00; if the Mac was asleep, it runs on wake (not if it was shut down).

## Your daily routine (about 5 minutes)

1. After the morning run the report opens by itself. Under **SUBMIT TO WHOP** are the
   posts that went live since the last report; paste each link into its campaign on Whop.
2. Under **CAMPAIGNS WORTH JOINING**, tap Join on any you like, then tell a Claude session:
   "add campaign <link>". It researches the footage and adds it to `campaigns.yaml`; your
   laptop picks it up on the next run (the run does `git pull` first).

Reports are saved in `~/clipper-data/reports/`. `python -m clipper links --days 7` reprints links.

## Settings (environment variables, all optional except the two Post for Me ones)

| Variable | Default | Meaning |
|---|---|---|
| `POSTFORME_API_KEY` | none | Post for Me key (required to publish) |
| `POSTFORME_ALLOWED_ACCOUNT_IDS` | none | Comma-separated Post for Me account IDs; empty = publishing disabled |
| `CLIPPER_SLOTS` | `08:15,12:15,17:15` | Post times, local time |
| `CLIPPER_TIMEZONE` | `Africa/Lagos` | |
| `CLIPPER_CLIPS_PER_DAY` | `3` | New clips per run |
| `CLIPPER_MIN_SCORE` | `7` | Average of Claude's hook/clarity/emotion scores (1–10) |
| `CLIPPER_WHISPER_MODEL` | `small` | `base` is faster, `medium` more accurate |
| `CLIPPER_DATA_DIR` | `~/clipper-data` | Where state, transcripts and reports live |
| `CLIPPER_MIN_FREE_GB` | `5` | Refuse to run below this much free disk |
| `CLIPPER_CLAUDE_MODEL` | Claude Code default | e.g. `sonnet` |
| `CLIPPER_OPEN_REPORT` | `1` | Open the report when there are links or failures |

## How it stays safe

- **Allowlist:** every create-post call checks the target against
  `POSTFORME_ALLOWED_ACCOUNT_IDS` and refuses anything else; an empty list disables publishing.
- **No double posts:** each post has a deterministic `external_id`; a DB row is written before
  the API call and Post for Me is checked for that ID on every retry or crash recovery.
- **YouTube quota:** Post for Me's YouTube uploads share a daily quota that resets at 08:00
  Lagos. A YouTube post that fails is retried at the next 08:15 slot, up to 3 attempts.
- **Brief compliance in code:** required text, mentions and hashtags are appended by code, not
  left to the model; banned terms, clip length and overlap are checked before rendering.
- **Secrets:** API responses are scrubbed of OAuth tokens before anything is logged.
- **Failures are isolated:** one clip failing never stops the run; all failures are listed in
  the report.

## Commands

```
python -m clipper daily [--dry-run]   # the daily run
python -m clipper check               # allowlist vs connected accounts
python -m clipper discover            # live Whop campaigns that fit your accounts
python -m clipper links [--days N]    # published URLs for Whop
pytest clipper/tests                  # unit tests
```
