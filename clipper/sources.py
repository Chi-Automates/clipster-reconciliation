"""Footage access: resolve campaign sources to videos, fetch audio for transcription,
and fetch only the exact video sections that become clips.

Full videos are never downloaded. Audio is ~50-60 MB per hour of footage and is deleted
right after transcription; each clip section is a few tens of MB and is deleted after upload.
"""
from __future__ import annotations

import hashlib
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}


@dataclass(frozen=True)
class SourceVideo:
    video_id: str
    url: str          # http(s) URL or absolute local path
    title: str
    duration: float | None

    @property
    def is_local(self) -> bool:
        return not self.url.startswith(("http://", "https://"))


def _local_id(path: Path) -> str:
    digest = hashlib.sha1(f"{path.name}:{path.stat().st_size}".encode()).hexdigest()[:12]
    return f"local-{digest}"


def _probe_duration(path: Path) -> float | None:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
            capture_output=True, text=True, timeout=60, check=True,
        )
        return float(out.stdout.strip())
    except (subprocess.SubprocessError, ValueError):
        return None


def resolve(source: str, max_items: int, inbox_dir: Path) -> list[SourceVideo]:
    """A source is a video URL, a channel/playlist URL, a local file, or a local folder."""
    if source.startswith(("http://", "https://")):
        return _resolve_url(source, max_items)
    path = Path(source).expanduser()
    if not path.is_absolute():
        path = inbox_dir / path
    files = sorted(p for p in path.iterdir() if p.suffix.lower() in VIDEO_EXTS) if path.is_dir() else [path]
    return [SourceVideo(_local_id(p), str(p.resolve()), p.stem, _probe_duration(p)) for p in files if p.exists()]


def _resolve_url(url: str, max_items: int) -> list[SourceVideo]:
    import yt_dlp

    opts = {"quiet": True, "no_warnings": True, "extract_flat": "in_playlist", "playlistend": max_items}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    entries = info.get("entries") if info.get("_type") in ("playlist", "multi_video") else [info]
    videos: list[SourceVideo] = []
    for e in entries or []:
        if not e or not e.get("id"):
            continue
        # A bare channel URL yields tabs (Videos, Shorts...) instead of videos; use the /videos URL.
        if e.get("ie_key") == "YoutubeTab":
            continue
        video_url = e.get("webpage_url") or e.get("url") or f"https://www.youtube.com/watch?v={e['id']}"
        videos.append(SourceVideo(e["id"], video_url, e.get("title") or e["id"], e.get("duration")))
    return videos[:max_items]


def fetch_audio(video: SourceVideo, audio_dir: Path) -> Path:
    """Audio-only download for transcription. Local files are transcribed in place."""
    if video.is_local:
        return Path(video.url)
    import yt_dlp

    existing = list(audio_dir.glob(f"{video.video_id}.*"))
    if existing:
        return existing[0]
    opts = {
        "quiet": True, "no_warnings": True, "noplaylist": True,
        "format": "bestaudio[ext=m4a]/bestaudio",
        "outtmpl": str(audio_dir / f"{video.video_id}.%(ext)s"),
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([video.url])
    files = list(audio_dir.glob(f"{video.video_id}.*"))
    if not files:
        raise RuntimeError(f"Audio download produced no file for {video.url}")
    return files[0]


def fetch_section(video: SourceVideo, start: float, end: float, dest: Path) -> Path:
    """Exactly [start, end] of the source at up to 1080p, as mp4."""
    if video.is_local:
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{start:.3f}", "-i", video.url,
             "-t", f"{end - start:.3f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
             "-c:a", "aac", "-b:a", "192k", str(dest)],
            check=True, timeout=900,
        )
        return dest
    import yt_dlp
    from yt_dlp.utils import download_range_func

    opts = {
        "quiet": True, "no_warnings": True, "noplaylist": True,
        "format": "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080]/bv*+ba/b",
        "merge_output_format": "mp4",
        "download_ranges": download_range_func(None, [(start, end)]),
        "force_keyframes_at_cuts": True,
        "outtmpl": str(dest.with_suffix("")) + ".%(ext)s",
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([video.url])
    produced = sorted(dest.parent.glob(dest.stem + ".*"), key=lambda p: p.stat().st_mtime)
    if not produced:
        raise RuntimeError(f"Section download produced no file for {video.url} {start}-{end}")
    if produced[-1] != dest:
        produced[-1].replace(dest)
    return dest
