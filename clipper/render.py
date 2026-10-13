"""1080x1920 render: framing, word-by-word burned captions (ASS), hook headline, loudness.

Styling varies slightly per clip (seeded by clip id) so a run of clips from one source
doesn't read as duplicate uploads to the platforms.
"""
from __future__ import annotations

import random
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

W, H = 1080, 1920
# ASS colours are &HAABBGGRR
HIGHLIGHTS = ["&H0000FFFF", "&H007FFF00", "&H00FFFF00", "&H0000A5FF", "&H00A040FF"]
HOOK_BOXES = [("&H00FFFFFF", "&H00000000"), ("&H0000FFFF", "&H00000000"), ("&H00000000", "&H00FFFFFF")]


@dataclass(frozen=True)
class Style:
    font: str
    font_size: int
    primary: str
    highlight: str
    outline: int
    shadow: int
    margin_v: int
    hook_box: str
    hook_text: str
    upper: bool
    words_per_chunk: int
    zoom: float
    saturation: float
    brightness: float


def style_for(clip_id: str, font: str = "Arial Black", framing: str = "blur") -> Style:
    """Blur framing: captions sit in the band just under the centred video, clear of the
    source's own lower thirds/watermarks. Crop framing: lower-middle of the frame.
    Both stay above the bottom ~20% that platform UI covers."""
    rng = random.Random(clip_id)
    box, text = rng.choice(HOOK_BOXES)
    return Style(
        font=font,
        font_size=rng.randint(74, 88),
        primary=rng.choice(["&H00FFFFFF", "&H00F2F2F2"]),
        highlight=rng.choice(HIGHLIGHTS),
        outline=rng.randint(5, 8),
        shadow=rng.randint(0, 3),
        margin_v=rng.randint(430, 520) if framing == "blur" else rng.randint(560, 720),
        hook_box=box,
        hook_text=text,
        upper=rng.random() < 0.7,
        words_per_chunk=rng.choice([2, 3]),
        zoom=round(rng.uniform(1.0, 1.12), 3),
        saturation=round(rng.uniform(1.0, 1.08), 3),
        brightness=round(rng.uniform(-0.02, 0.02), 3),
    )


def _ts(seconds: float) -> str:
    seconds = max(0.0, seconds)
    cs = int(round(seconds * 100))
    h, rem = divmod(cs, 360000)
    m, rem = divmod(rem, 6000)
    s, cs = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _esc(text: str) -> str:
    return text.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ")


def chunk_words(words: list[dict], size: int, max_gap: float = 0.6) -> list[list[dict]]:
    chunks: list[list[dict]] = []
    current: list[dict] = []
    for w in words:
        gap = w["start"] - current[-1]["end"] if current else 0
        if current and (len(current) >= size or gap > max_gap or re.search(r"[.?!]$", current[-1]["word"])):
            chunks.append(current)
            current = []
        current.append(w)
    if current:
        chunks.append(current)
    return chunks


def build_ass(words: list[dict], hook_text: str, duration: float, style: Style) -> str:
    """`words` have start/end in seconds relative to the clip start."""
    s = style
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,{s.font},{s.font_size},{s.primary},{s.primary},&H00000000,&H96000000,-1,0,0,0,100,100,0,0,1,{s.outline},{s.shadow},2,80,140,{s.margin_v},1
Style: Hook,{s.font},62,{s.hook_text},{s.hook_text},{s.hook_box},&H00000000,-1,0,0,0,100,100,0,0,3,16,0,8,90,90,230,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    if hook_text.strip():
        hook = _esc(hook_text.strip().upper() if s.upper else hook_text.strip())
        lines.append(f"Dialogue: 1,{_ts(0)},{_ts(duration)},Hook,,0,0,0,,{hook}")
    chunks = chunk_words(words, s.words_per_chunk)
    for ci, chunk in enumerate(chunks):
        next_start = chunks[ci + 1][0]["start"] if ci + 1 < len(chunks) else duration
        tokens = [_esc(w["word"].upper() if s.upper else w["word"]) for w in chunk]
        for wi, w in enumerate(chunk):
            start = w["start"]
            if wi + 1 < len(chunk):
                end = chunk[wi + 1]["start"]
            else:  # hold the last word until the next chunk if the pause is short
                end = next_start if next_start - w["end"] < 0.35 else w["end"] + 0.15
            if end <= start:
                end = start + 0.08
            text = " ".join(
                f"{{\\c{s.highlight}\\fscx108\\fscy108}}{t}{{\\c{s.primary}\\fscx100\\fscy100}}" if i == wi else t
                for i, t in enumerate(tokens)
            )
            lines.append(f"Dialogue: 0,{_ts(start)},{_ts(min(end, duration))},Caption,,0,0,0,,{text}")
    return header + "\n".join(lines) + "\n"


def video_filter(framing: str, crop_x: float, style: Style) -> str:
    z = style.zoom
    if framing == "crop":
        h = int(H * z) // 2 * 2
        base = (f"[0:v]scale=-2:{h},crop={W}:{H}:x='(iw-{W})*{min(max(crop_x, 0), 1)}':y='(ih-{H})/2'[v0]")
    else:
        fg_w = int(W * z) // 2 * 2
        base = (f"[0:v]split[a][b];"
                f"[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},gblur=sigma=28,"
                f"eq=brightness=-0.08[bg];"
                f"[b]scale={fg_w}:-2,crop='min(iw,{W})':ih[fg];"
                f"[bg][fg]overlay=(W-w)/2:(H-h)/2[v0]")
    return (f"{base};[v0]eq=saturation={style.saturation}:brightness={style.brightness},"
            f"setsar=1,ass=captions.ass,format=yuv420p[vout]")


def render(section: Path, out: Path, words: list[dict], hook_text: str, duration: float,
           framing: str, crop_x: float, clip_id: str, font: str = "Arial Black") -> Path:
    style = style_for(clip_id, font, framing)
    work = section.parent
    (work / "captions.ass").write_text(build_ass(words, hook_text, duration, style), encoding="utf-8")
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(section.resolve()),
        "-filter_complex", video_filter(framing, crop_x, style),
        "-map", "[vout]", "-map", "0:a:0?",
        "-af", "loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000",
        "-t", f"{duration:.3f}", "-r", "30",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-profile:v", "high",
        "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out.resolve()),
    ]
    # Run inside the work dir so the ass filter gets a plain relative path (avoids Windows drive-letter escaping).
    proc = subprocess.run(cmd, cwd=work, timeout=1800, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg render failed: {proc.stderr.strip()[-800:]}")
    return out
