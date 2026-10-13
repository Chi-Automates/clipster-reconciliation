"""Campaign definitions loaded from campaigns.yaml."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

SUPPORTED_PLATFORMS = ("youtube", "instagram", "x", "tiktok", "facebook")


@dataclass(frozen=True)
class Campaign:
    id: str
    name: str
    active: bool
    whop_url: str
    cpm: float
    platforms: tuple[str, ...]
    sources: tuple[str, ...]
    brief: str = ""
    framing: str = "blur"            # blur | crop
    crop_x: float = 0.5              # 0 = left edge, 1 = right edge (crop framing only)
    min_seconds: int = 20
    max_seconds: int = 60
    required_text: str = ""          # appended verbatim to every caption / description
    required_hashtags: tuple[str, ...] = ()
    required_mentions: tuple[str, ...] = ()
    banned: tuple[str, ...] = ()
    max_videos_per_source: int = 5
    extra: dict = field(default_factory=dict)


def _tuple(value) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(str(v) for v in value)


def load_campaigns(path: Path) -> list[Campaign]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    campaigns: list[Campaign] = []
    seen: set[str] = set()
    for item in raw.get("campaigns", []) or []:
        cid = str(item["id"]).strip()
        if cid in seen:
            raise ValueError(f"Duplicate campaign id in {path}: {cid}")
        seen.add(cid)
        platforms = tuple(p.lower() for p in _tuple(item.get("platforms")))
        unknown = [p for p in platforms if p not in SUPPORTED_PLATFORMS]
        if unknown:
            raise ValueError(f"Campaign {cid}: unknown platforms {unknown}")
        clip_range = item.get("clip_seconds", [20, 60])
        framing = str(item.get("framing", "blur")).lower()
        if framing not in ("blur", "crop"):
            raise ValueError(f"Campaign {cid}: framing must be blur or crop")
        campaigns.append(Campaign(
            id=cid,
            name=str(item.get("name", cid)),
            active=bool(item.get("active", False)),
            whop_url=str(item.get("whop_url", "")),
            cpm=float(item.get("cpm", 0) or 0),
            platforms=platforms,
            sources=_tuple(item.get("sources")),
            brief=str(item.get("brief", "") or ""),
            framing=framing,
            crop_x=float(item.get("crop_x", 0.5)),
            min_seconds=int(clip_range[0]),
            max_seconds=int(clip_range[1]),
            required_text=str(item.get("required_text", "") or "").strip(),
            required_hashtags=tuple(h if h.startswith("#") else f"#{h}" for h in _tuple(item.get("required_hashtags"))),
            required_mentions=tuple(m if m.startswith("@") else f"@{m}" for m in _tuple(item.get("required_mentions"))),
            banned=tuple(b.lower() for b in _tuple(item.get("banned"))),
            max_videos_per_source=int(item.get("max_videos_per_source", 5)),
            extra={k: v for k, v in item.items() if k not in Campaign.__dataclass_fields__},
        ))
    return campaigns
