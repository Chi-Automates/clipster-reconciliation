"""Campaign discovery from Whop's public Content Rewards feed.

Joining stays manual (it has to happen from your Whop account). This only shortlists
clipping campaigns that pay on platforms you can post to, ranked by rate and budget.
Scraping public HTML is brittle by nature: any failure here is reported, never fatal.
"""
from __future__ import annotations

import html
import logging
import re
from dataclasses import dataclass

import requests

log = logging.getLogger(__name__)

FEED_URL = "https://whop.com/contentrewards/"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128 Safari/537.36"
# Campaigns that need you on camera, per-clip manual verification, or original UGC can't be automated.
SKIP_PATTERNS = re.compile(
    r"\bugc\b|film (?:it|yourself)|on camera|face ?cam|vouch|screen recording|record yourself|"
    r"contenu ugc|slideshow|your own (?:video|content)",
    re.I,
)
FEED_RE = re.compile(
    r"@ contentrewardsbot · \S+ (?P<name>.*?) Budget: \$(?P<budget>[\d,]+) CPM: \$(?P<cpm>[\d.]+) per 1,000 views "
    r"Platforms: (?P<platforms>[A-Za-z, ]+?) Campaign link: (?P<url>https://contentrewards\.com/c/campaigns/[0-9a-f-]+)"
)


@dataclass
class Listing:
    name: str
    url: str
    cpm: float
    budget: float
    platforms: list[str]
    description: str = ""
    skip_reason: str = ""

    @property
    def rank(self) -> float:
        return self.cpm * min(self.budget, 5000)


def _text(page: str) -> str:
    page = re.sub(r"<script.*?</script>|<style.*?</style>", " ", page, flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", page)))


def _get(url: str) -> str:
    resp = requests.get(url, headers={"User-Agent": UA}, timeout=30)
    resp.raise_for_status()
    return resp.text


def parse_feed(page_text: str) -> list[Listing]:
    out: dict[str, Listing] = {}
    for m in FEED_RE.finditer(page_text):
        platforms = [p.strip().lower() for p in m["platforms"].split(",") if p.strip()]
        out.setdefault(m["url"], Listing(
            name=m["name"].strip(), url=m["url"], cpm=float(m["cpm"]),
            budget=float(m["budget"].replace(",", "")), platforms=platforms,
        ))
    return list(out.values())


def campaign_description(page_text: str) -> str:
    start = page_text.find("Join Campaign")
    end = page_text.find("Accepting clips")
    if start == -1 or end == -1 or end <= start:
        return ""
    return page_text[start + len("Join Campaign"):end].strip()


def shortlist(my_platforms: set[str], max_pages: int = 15) -> list[Listing]:
    listings = parse_feed(_text(_get(FEED_URL)))
    for item in listings[:max_pages]:
        try:
            item.description = campaign_description(_text(_get(item.url)))[:600]
        except requests.RequestException as exc:
            log.warning("Could not read %s: %s", item.url, exc)
    for item in listings:
        fits = my_platforms & {p.replace("twitter", "x") for p in item.platforms}
        if not fits:
            item.skip_reason = f"pays only on {', '.join(item.platforms)}"
        elif SKIP_PATTERNS.search(f"{item.name} {item.description}"):
            item.skip_reason = "needs on-camera/UGC or manual verification"
    return sorted(listings, key=lambda i: (bool(i.skip_reason), -i.rank))
