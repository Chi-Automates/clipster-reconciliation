"""Moment selection with Claude Code in headless mode (`claude -p`), using your Claude login.

Claude proposes candidates; everything that matters for compliance (length, overlap,
required text, banned words, score threshold) is enforced here in code, not trusted.
"""
from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass

from .campaigns import Campaign

log = logging.getLogger(__name__)

CLIP_SCHEMA = {
    "type": "object",
    "properties": {
        "clips": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start": {"type": "number"},
                    "end": {"type": "number"},
                    "hook_text": {"type": "string"},
                    "title": {"type": "string"},
                    "caption": {"type": "string"},
                    "hashtags": {"type": "array", "items": {"type": "string"}},
                    "hook_score": {"type": "number"},
                    "clarity_score": {"type": "number"},
                    "emotion_score": {"type": "number"},
                    "reasoning": {"type": "string"},
                },
                "required": ["start", "end", "hook_text", "title", "caption", "hashtags",
                             "hook_score", "clarity_score", "emotion_score", "reasoning"],
            },
        }
    },
    "required": ["clips"],
}

PROMPT = """You are the editor for a short-form clipping channel paid per view (Whop Content Rewards).
Pick the {count} moments from the transcript below most likely to go viral as standalone 9:16 shorts.

Campaign: {name}
Campaign brief (follow it exactly):
{brief}

Hard rules:
- Each clip is {min_s}-{max_s} seconds long. start/end are seconds from the transcript timestamps.
- Start exactly where the hook starts: the first 2 seconds must grab attention on their own
  (a bold claim, a number, a conflict, a famous name, a question). No warm-up, no "so, um".
- The clip must make sense to someone who never saw the episode, and end on a payoff, not mid-thought.
- Do not overlap these already-used ranges (seconds): {used}
- Prefer: money figures, celebrities and brands, confrontation, surprising confessions, strong opinions.
- Never misrepresent what was said; titles and captions must be true to the clip.

For each clip return:
- hook_text: 3-7 word on-screen headline shown at the top of the video (no hashtags, no emojis).
- title: YouTube Shorts title, max 90 characters, curiosity-driven, no clickbait lies.
- caption: 1-2 punchy sentences for Instagram/YouTube. Do NOT add the campaign's required text; it is appended automatically.
- hashtags: 3-6 relevant hashtags without the # sign.
- hook_score, clarity_score, emotion_score: 1-10, be harsh. 8+ means you would bet on it.
- reasoning: one sentence.

Transcript ([start-end] seconds, text):
{transcript}
"""


@dataclass
class Candidate:
    start: float
    end: float
    score: float
    hook_text: str
    title: str
    caption: str
    hashtags: list[str]
    reasoning: str


def transcript_text(transcript: dict) -> str:
    return "\n".join(f"[{s['start']:.1f}-{s['end']:.1f}] {s['text']}" for s in transcript["segments"])


def ask_claude(prompt: str, claude_bin: str, model: str | None, timeout: int = 900) -> list[dict]:
    exe = shutil.which(claude_bin) or claude_bin
    cmd = [exe, "-p", "--tools", "", "--no-session-persistence", "--output-format", "json",
           "--json-schema", json.dumps(CLIP_SCHEMA)]
    if model:
        cmd += ["--model", model]
    with tempfile.TemporaryDirectory() as cwd:  # empty dir: no project files or CLAUDE.md pulled in
        proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8",
                              timeout=timeout, cwd=cwd)
    if proc.returncode != 0:
        raise RuntimeError(f"claude -p failed (exit {proc.returncode}): {(proc.stderr or proc.stdout)[:500]}")
    envelope = json.loads(proc.stdout)
    if envelope.get("is_error"):
        raise RuntimeError(f"claude -p returned an error: {str(envelope.get('result'))[:500]}")
    data = envelope.get("structured_output")
    if data is None:
        data = json.loads(envelope.get("result") or "{}")
    return list(data.get("clips", []))


def snap(transcript: dict, start: float, end: float) -> tuple[float, float] | None:
    """Move boundaries onto word edges: first word starting at/after start, last word ending by end."""
    words = [w for s in transcript["segments"] for w in s["words"]]
    inside = [w for w in words if w["start"] >= start - 0.3 and w["end"] <= end + 0.3]
    if not inside:
        return None
    return max(0.0, inside[0]["start"] - 0.05), inside[-1]["end"] + 0.25


def overlaps(a: tuple[float, float], b: tuple[float, float], margin: float = 1.0) -> bool:
    return a[0] < b[1] + margin and b[0] < a[1] + margin


def clean_tag(tag: str) -> str:
    return re.sub(r"[^\w]", "", tag.lstrip("#"))


def validate(raw: list[dict], transcript: dict, campaign: Campaign, used: list[tuple[float, float]],
             min_score: float) -> tuple[list[Candidate], list[str]]:
    accepted: list[Candidate] = []
    rejected: list[str] = []
    taken = list(used)
    for c in sorted(raw, key=lambda c: -(c["hook_score"] + c["clarity_score"] + c["emotion_score"])):
        label = f"{c.get('start')}-{c.get('end')} '{c.get('title', '')[:40]}'"
        snapped = snap(transcript, float(c["start"]), float(c["end"]))
        if not snapped:
            rejected.append(f"{label}: no words in range")
            continue
        start, end = snapped
        if not (campaign.min_seconds <= end - start <= campaign.max_seconds):
            rejected.append(f"{label}: length {end - start:.0f}s outside {campaign.min_seconds}-{campaign.max_seconds}s")
            continue
        if any(overlaps((start, end), t) for t in taken):
            rejected.append(f"{label}: overlaps a used segment")
            continue
        score = round((c["hook_score"] + c["clarity_score"] + c["emotion_score"]) / 3, 2)
        if score < min_score:
            rejected.append(f"{label}: score {score} below {min_score}")
            continue
        spoken = " ".join(w["word"] for s in transcript["segments"] for w in s["words"]
                          if w["start"] >= start and w["end"] <= end).lower()
        text = f"{c['title']} {c['caption']} {c['hook_text']} {spoken}".lower()
        hit = next((b for b in campaign.banned if b in text), None)
        if hit:
            rejected.append(f"{label}: contains banned term '{hit}'")
            continue
        tags = [t for t in (clean_tag(h) for h in c["hashtags"]) if t][:6]
        accepted.append(Candidate(start, end, score, c["hook_text"].strip(), c["title"].strip()[:95],
                                  c["caption"].strip(), tags, c.get("reasoning", "").strip()))
        taken.append((start, end))
    return accepted, rejected


def select(transcript: dict, campaign: Campaign, used: list[tuple[float, float]], *, count: int,
           claude_bin: str, model: str | None, min_score: float) -> tuple[list[Candidate], list[str]]:
    used_txt = ", ".join(f"{a:.0f}-{b:.0f}" for a, b in used) or "none"
    prompt = PROMPT.format(
        count=count, name=campaign.name, brief=campaign.brief.strip() or "(no extra rules)",
        min_s=campaign.min_seconds, max_s=campaign.max_seconds, used=used_txt,
        transcript=transcript_text(transcript),
    )
    raw = ask_claude(prompt, claude_bin, model)
    return validate(raw, transcript, campaign, used, min_score)


def build_caption(campaign: Campaign, caption: str, hashtags: list[str], platform: str) -> str:
    """Final caption per platform; required text, mentions and hashtags are always present."""
    tags = list(dict.fromkeys([*campaign.required_hashtags, *(f"#{t}" for t in hashtags)]))
    parts = [caption.strip()]
    if campaign.required_mentions:
        parts.append(" ".join(campaign.required_mentions))
    if campaign.required_text:
        parts.append(campaign.required_text)
    body = "\n\n".join(p for p in parts if p)
    if platform == "x":
        required = "\n\n".join(p for p in parts[1:] if p)
        budget = 280 - len(required) - (2 if required else 0)
        head = parts[0] if len(parts[0]) <= budget else parts[0][: max(0, budget - 1)].rstrip() + "…"
        body = "\n\n".join(p for p in (head, required) if p)
        for t in tags:
            if len(body) + 1 + len(t) <= 280:
                body += f" {t}"
        return body
    return f"{body}\n\n{' '.join(tags)}".strip()
