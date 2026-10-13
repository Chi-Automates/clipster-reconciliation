"""The daily run: results -> retries -> new clips -> schedule -> report -> cleanup.

One clip failing never stops the run; every failure is listed in the report.
"""
from __future__ import annotations

import json
import logging
import shutil
import sqlite3
import traceback
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from . import db, discover, render, selector, sources, transcribe
from .campaigns import Campaign, load_campaigns
from .config import Settings
from .postforme import NotAllowedError, PostForMe, expiring_accounts

log = logging.getLogger(__name__)
CANDIDATES_PER_ROUND = 8
MAX_SELECT_ROUNDS = 2
POSTABLE = ("youtube", "instagram", "x", "tiktok", "facebook")


@dataclass
class RunReport:
    dry_run: bool
    scheduled: list[str] = field(default_factory=list)
    published: dict[str, list[str]] = field(default_factory=dict)   # campaign -> urls
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    shortlist: list[discover.Listing] = field(default_factory=list)
    dry_run_files: list[str] = field(default_factory=list)
    dry_used: set[str] = field(default_factory=set)


# --------------------------------------------------------------------------- slots
def upcoming_slots(settings: Settings, now: datetime, taken: set[str], count: int,
                   lead: timedelta = timedelta(minutes=20), first_only: bool = False) -> list[datetime]:
    """Next free slot times (UTC) within the next 24h, skipping slots already used.
    first_only: only the day's first slot (YouTube retries go right after its quota reset)."""
    tz = settings.timezone
    local_now = now.astimezone(tz)
    found: list[datetime] = []
    for day_offset in (0, 1):
        day: date = (local_now + timedelta(days=day_offset)).date()
        for hhmm in settings.slots[:1] if first_only else settings.slots:
            hh, mm = (int(x) for x in hhmm.split(":"))
            at = datetime.combine(day, time(hh, mm), tz).astimezone(timezone.utc)
            if at < now + lead or at > now + timedelta(hours=24):
                continue
            if at.isoformat(timespec="seconds") in taken:
                continue
            found.append(at)
            if len(found) == count:
                return found
    return found


def taken_slots(conn: sqlite3.Connection) -> set[str]:
    return {r["slot_at"] for r in conn.execute("SELECT slot_at FROM clips WHERE slot_at IS NOT NULL")}


# --------------------------------------------------------------------------- posting
def payload_for(campaign: Campaign, clip: sqlite3.Row, platform: str, account_id: str,
                scheduled_at: str, external_id: str) -> dict:
    caption = selector.build_caption(campaign, clip["caption"], (clip["hashtags"] or "").split(), platform)
    payload: dict = {
        "caption": caption,
        "social_accounts": [account_id],
        "media": [{"url": clip["media_url"]}],
        "scheduled_at": scheduled_at,
        "external_id": external_id,
    }
    if platform == "youtube":
        payload["platform_configurations"] = {"youtube": {
            "title": clip["title"][:100], "description": caption, "privacy_status": "public",
            "made_for_kids": False, "tags": (clip["hashtags"] or "").split()[:10],
        }}
    elif platform == "instagram":
        payload["platform_configurations"] = {"instagram": {"placement": "reels", "share_to_feed": True}}
    return payload


def create_post_once(conn: sqlite3.Connection, pfm: PostForMe, campaign: Campaign, clip: sqlite3.Row,
                     platform: str, account_id: str, scheduled_at: str, attempt: int) -> str:
    """Idempotent: a row is written before the API call, and on any re-run the external_id
    is looked up in Post for Me first, so a crash between the two can never double-post."""
    external_id = f"{clip['clip_id']}.{platform}.a{attempt}"
    row = conn.execute("SELECT * FROM posts WHERE external_id = ?", (external_id,)).fetchone()
    if row and row["pfm_post_id"]:
        return row["pfm_post_id"]
    if not row:
        ts = db.now_iso()
        conn.execute(
            """INSERT INTO posts (clip_id, campaign_id, platform, account_id, attempt, external_id,
               scheduled_at, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, 'creating', ?, ?)""",
            (clip["clip_id"], campaign.id, platform, account_id, attempt, external_id, scheduled_at, ts, ts),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM posts WHERE external_id = ?", (external_id,)).fetchone()
    existing = pfm.find_by_external_id(external_id)
    post = existing or pfm.create_post(payload_for(campaign, clip, platform, account_id, scheduled_at, external_id))
    db.update_post(conn, row["id"], pfm_post_id=post["id"], status="scheduled")
    return post["id"]


def collect_results(conn: sqlite3.Connection, pfm: PostForMe, report: RunReport) -> None:
    due = conn.execute(
        "SELECT * FROM posts WHERE status = 'scheduled' AND scheduled_at <= ? AND pfm_post_id IS NOT NULL",
        (db.now_iso(),),
    ).fetchall()
    if not due:
        return
    by_post = {r["pfm_post_id"]: r for r in due}
    for res in pfm.results_for(list(by_post)):
        row = by_post.get(res.get("post_id"))
        if not row:
            continue
        if res.get("success"):
            db.update_post(conn, row["id"], status="published", url=(res.get("platform_data") or {}).get("url"))
        else:
            err = str(res.get("error") or "unknown error")
            db.update_post(conn, row["id"], status="failed", error=err[:1000])
            report.failures.append(f"{row['platform']} post for clip {row['clip_id']} failed: {err[:200]}")


def retry_failed(conn: sqlite3.Connection, pfm: PostForMe, campaigns: dict[str, Campaign],
                 accounts: dict, settings: Settings, report: RunReport) -> None:
    failed = conn.execute(
        """SELECT p.* FROM posts p WHERE p.status = 'failed' AND NOT EXISTS (
             SELECT 1 FROM posts q WHERE q.clip_id = p.clip_id AND q.platform = p.platform
             AND q.attempt > p.attempt)""",
    ).fetchall()
    for row in failed:
        campaign = campaigns.get(row["campaign_id"])
        acct = accounts.get(row["platform"])
        clip = conn.execute("SELECT * FROM clips WHERE clip_id = ?", (row["clip_id"],)).fetchone()
        if not campaign or not acct or not clip or not clip["media_url"]:
            continue
        if row["attempt"] >= settings.max_post_attempts:
            report.warnings.append(f"Gave up on {row['platform']} for clip {row['clip_id']} after {row['attempt']} attempts")
            db.update_post(conn, row["id"], status="superseded")
            continue
        slot = upcoming_slots(settings, datetime.now(timezone.utc), set(), 1,
                              first_only=row["platform"] == "youtube")
        when = (slot[0] if slot else datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(timespec="seconds")
        try:
            create_post_once(conn, pfm, campaign, clip, row["platform"], acct.id, when, row["attempt"] + 1)
            db.update_post(conn, row["id"], status="superseded")
            report.scheduled.append(f"RETRY {row['platform']} '{clip['title']}' at {when}")
        except Exception as exc:  # noqa: BLE001 - reported, never fatal
            report.failures.append(f"Retry of {row['platform']} for clip {row['clip_id']}: {exc}")


def recover_creating(conn: sqlite3.Connection, pfm: PostForMe, campaigns: dict[str, Campaign],
                     report: RunReport) -> None:
    """Rows left in 'creating' by a crash: adopt the post if Post for Me has it, else create it."""
    for row in conn.execute("SELECT * FROM posts WHERE status = 'creating'").fetchall():
        campaign = campaigns.get(row["campaign_id"])
        clip = conn.execute("SELECT * FROM clips WHERE clip_id = ?", (row["clip_id"],)).fetchone()
        if not campaign or not clip or not clip["media_url"]:
            continue
        try:
            create_post_once(conn, pfm, campaign, clip, row["platform"], row["account_id"],
                             row["scheduled_at"], row["attempt"])
        except NotAllowedError:
            raise
        except Exception as exc:  # noqa: BLE001
            report.failures.append(f"Could not recover {row['platform']} post for clip {row['clip_id']}: {exc}")


# --------------------------------------------------------------------------- clips
def next_candidate(conn: sqlite3.Connection, settings: Settings, campaign: Campaign, report: RunReport,
                   exclude: set[str]) -> tuple[sqlite3.Row, sources.SourceVideo, dict] | None:
    """Best unused candidate for a campaign, transcribing/selecting more material as needed."""
    inbox = settings.subdir("inbox")
    for src in campaign.sources:
        try:
            videos = sources.resolve(src, campaign.max_videos_per_source, inbox)
        except Exception as exc:  # noqa: BLE001
            report.failures.append(f"[{campaign.id}] could not read source {src}: {exc}")
            continue
        for video in videos:
            vrow = db.upsert_video(conn, video.video_id, campaign.id, video.url, video.title, video.duration)
            if vrow["status"] in ("exhausted", "failed"):
                continue
            try:
                transcript = ensure_transcript(conn, settings, video)
            except Exception as exc:  # noqa: BLE001
                db.update_video(conn, video.video_id, status="failed", error=str(exc)[:500])
                report.failures.append(f"[{campaign.id}] transcription failed for {video.title}: {exc}")
                continue
            for _ in range(50):
                params = (video.video_id, campaign.id, *exclude)
                cand = conn.execute(
                    "SELECT * FROM clips WHERE video_id = ? AND campaign_id = ? AND status = 'candidate' "
                    f"AND clip_id NOT IN ({','.join('?' * len(exclude))}) ORDER BY score DESC LIMIT 1",
                    params,
                ).fetchone()
                if cand:
                    if any(selector.overlaps((cand["start"], cand["end"]), u)
                           for u in db.used_ranges(conn, video.video_id)):
                        db.update_clip(conn, cand["clip_id"], status="rejected", reason="overlaps used segment")
                        continue
                    return cand, video, transcript
                rounds = conn.execute("SELECT select_rounds FROM videos WHERE video_id = ?",
                                      (video.video_id,)).fetchone()["select_rounds"]
                if rounds >= MAX_SELECT_ROUNDS:
                    db.update_video(conn, video.video_id, status="exhausted")
                    break
                try:
                    add_candidates(conn, settings, campaign, video, transcript, report)
                except Exception as exc:  # noqa: BLE001 - e.g. claude CLI not logged in
                    report.failures.append(f"[{campaign.id}] clip selection failed for {video.title}: {exc}")
                    break
                db.update_video(conn, video.video_id, select_rounds=rounds + 1)
    return None


def ensure_transcript(conn: sqlite3.Connection, settings: Settings, video: sources.SourceVideo) -> dict:
    cache = settings.subdir("transcripts") / f"{video.video_id}.json"
    if not cache.exists():
        log.info("Transcribing %s", video.title)
        audio = sources.fetch_audio(video, settings.subdir("audio"))
        try:
            transcribe.transcribe(audio, cache, settings.whisper_model)
        finally:
            if not video.is_local:
                audio.unlink(missing_ok=True)
        db.update_video(conn, video.video_id, transcript=str(cache), status="transcribed")
    return json.loads(cache.read_text(encoding="utf-8"))


def add_candidates(conn: sqlite3.Connection, settings: Settings, campaign: Campaign,
                   video: sources.SourceVideo, transcript: dict, report: RunReport) -> None:
    used = [(r["start"], r["end"]) for r in conn.execute(
        "SELECT start, end FROM clips WHERE video_id = ? AND status != 'rejected'", (video.video_id,))]
    log.info("Asking Claude for moments in %s", video.title)
    accepted, rejected = selector.select(
        transcript, campaign, used, count=CANDIDATES_PER_ROUND, claude_bin=settings.claude_bin,
        model=settings.claude_model, min_score=settings.min_score,
    )
    ts = db.now_iso()
    for c in accepted:
        clip_id = f"{video.video_id}_{int(c.start)}_{int(c.end)}"
        conn.execute(
            """INSERT OR IGNORE INTO clips (clip_id, campaign_id, video_id, start, end, score, hook_text, title,
               caption, hashtags, reasoning, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'candidate', ?, ?)""",
            (clip_id, campaign.id, video.video_id, c.start, c.end, c.score, c.hook_text, c.title,
             c.caption, " ".join(c.hashtags), c.reasoning, ts, ts),
        )
    conn.commit()
    log.info("%d candidates accepted, %d rejected for %s", len(accepted), len(rejected), video.title)
    for r in rejected:
        log.info("  rejected %s", r)


def produce_clip(conn: sqlite3.Connection, settings: Settings, pfm: PostForMe | None, campaign: Campaign,
                 accounts: dict, slot: datetime, report: RunReport) -> bool:
    targets = [p for p in campaign.platforms if p in accounts]
    if not targets:
        report.warnings.append(f"[{campaign.id}] none of its platforms ({', '.join(campaign.platforms)}) "
                               "are connected and allowlisted; skipped")
        return False
    found = next_candidate(conn, settings, campaign, report, report.dry_used)
    if not found:
        return False
    clip, video, transcript = found
    work = settings.subdir("work") / clip["clip_id"]
    work.mkdir(parents=True, exist_ok=True)
    out = settings.subdir("out") / f"{clip['clip_id']}.mp4"
    try:
        section = sources.fetch_section(video, clip["start"], clip["end"], work / "section.mp4")
        words = [{**w, "start": w["start"] - clip["start"], "end": w["end"] - clip["start"]}
                 for w in transcribe.words_between(transcript, clip["start"], clip["end"])]
        render.render(section, out, words, clip["hook_text"] or "", clip["end"] - clip["start"],
                      campaign.framing, campaign.crop_x, clip["clip_id"])
        slot_iso = slot.isoformat(timespec="seconds")
        if report.dry_run:
            report.dry_used.add(clip["clip_id"])  # stays a candidate for the real run
            report.dry_run_files.append(str(out))
            for p in targets:
                caption = selector.build_caption(campaign, clip["caption"], (clip["hashtags"] or "").split(), p)
                report.scheduled.append(
                    f"[DRY RUN] {p} -> {accounts[p].username} at {slot.astimezone(settings.timezone):%a %H:%M}: "
                    f"'{clip['title']}' (score {clip['score']})\n      caption: {caption[:160]!r}")
            return True
        db.update_clip(conn, clip["clip_id"], status="rendered")
        media_url = pfm.upload(out)
        db.update_clip(conn, clip["clip_id"], media_url=media_url, slot_at=slot_iso)
        clip = conn.execute("SELECT * FROM clips WHERE clip_id = ?", (clip["clip_id"],)).fetchone()
        for p in targets:
            try:
                create_post_once(conn, pfm, campaign, clip, p, accounts[p].id, slot_iso, attempt=1)
                report.scheduled.append(
                    f"{p} @{accounts[p].username} at {slot.astimezone(settings.timezone):%a %H:%M}: '{clip['title']}'")
            except NotAllowedError:
                raise
            except Exception as exc:  # noqa: BLE001
                report.failures.append(f"[{campaign.id}] {p} schedule failed for {clip['clip_id']}: {exc}")
        db.update_clip(conn, clip["clip_id"], status="queued")
        out.unlink(missing_ok=True)
        return True
    except NotAllowedError:
        raise
    except Exception as exc:  # noqa: BLE001
        db.update_clip(conn, clip["clip_id"], status="failed", reason=str(exc)[:500])
        report.failures.append(f"[{campaign.id}] clip {clip['clip_id']} failed: {exc}")
        log.debug(traceback.format_exc())
        return True  # slot attempted; move on
    finally:
        shutil.rmtree(work, ignore_errors=True)


# --------------------------------------------------------------------------- report & cleanup
def gather_published(conn: sqlite3.Connection, campaigns: dict[str, Campaign], report: RunReport) -> None:
    rows = conn.execute("SELECT * FROM posts WHERE status = 'published' AND reported = 0 ORDER BY scheduled_at").fetchall()
    for r in rows:
        c = campaigns.get(r["campaign_id"])
        key = f"{c.name if c else r['campaign_id']}  ({c.whop_url if c else ''})"
        report.published.setdefault(key, []).append(f"{r['platform']}: {r['url']}")
        if not report.dry_run:
            db.update_post(conn, r["id"], reported=1)


def cleanup(settings: Settings) -> None:
    cutoff = datetime.now().timestamp() - settings.transcript_keep_days * 86400
    for f in settings.subdir("transcripts").glob("*.json"):
        if f.stat().st_mtime < cutoff:
            f.unlink(missing_ok=True)
    for f in settings.subdir("out").glob("*.mp4"):  # dry-run renders are kept 3 days for review
        if f.stat().st_mtime < datetime.now().timestamp() - 3 * 86400:
            f.unlink(missing_ok=True)
    shutil.rmtree(settings.data_dir / "work", ignore_errors=True)


def format_report(report: RunReport, settings: Settings) -> str:
    now = datetime.now(settings.timezone)
    out = [f"CLIPPER REPORT  {now:%Y-%m-%d %H:%M} ({settings.timezone.key}){'  [DRY RUN]' if report.dry_run else ''}", ""]
    out.append("SUBMIT TO WHOP (new published posts):")
    if report.published:
        for campaign, urls in report.published.items():
            out.append(f"  {campaign}")
            out.extend(f"    {u}" for u in urls)
    else:
        out.append("  none yet")
    out += ["", "SCHEDULED THIS RUN:"] + ([f"  {s}" for s in report.scheduled] or ["  none"])
    if report.dry_run_files:
        out += ["", "DRY-RUN RENDERS (review these):"] + [f"  {f}" for f in report.dry_run_files]
    picks = [l for l in report.shortlist if not l.skip_reason][:5]
    if picks:
        out += ["", "CAMPAIGNS WORTH JOINING (tap Join, then tell Claude to add them):"]
        out += [f"  ${l.cpm}/1K  ${l.budget:,.0f} budget  {'/'.join(l.platforms)}  {l.name}\n    {l.url}" for l in picks]
    if report.warnings:
        out += ["", "WARNINGS:"] + [f"  {w}" for w in report.warnings]
    out += ["", "FAILURES:"] + ([f"  {f}" for f in report.failures] or ["  none"])
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------- entry point
def run_daily(settings: Settings, dry_run: bool = False) -> tuple[RunReport, Path]:
    report = RunReport(dry_run=dry_run)
    free_gb = shutil.disk_usage(settings.data_dir).free / 1e9
    if free_gb < settings.min_free_gb:
        raise SystemExit(f"Only {free_gb:.1f} GB free; need {settings.min_free_gb} GB. Free space or lower CLIPPER_MIN_FREE_GB.")
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg not found on PATH")

    conn = db.connect(settings.db_path)
    campaigns = {c.id: c for c in load_campaigns(settings.campaigns_file)}
    active = sorted((c for c in campaigns.values() if c.active), key=lambda c: -c.cpm)

    pfm = PostForMe(settings.api_key, settings.allowed_account_ids)
    try:
        all_accounts = pfm.accounts()
        report.warnings += expiring_accounts([a for a in all_accounts if a.id in settings.allowed_account_ids])
        accounts = pfm.allowed_accounts()
    except Exception as exc:  # noqa: BLE001 - a real run stops here; NotAllowedError is a safety stop
        if not dry_run:
            raise
        report.warnings.append(f"Post for Me account check unavailable ({exc}); dry run uses placeholder accounts")
        accounts = {}
    my_platforms = set(accounts) or {"youtube", "instagram", "x"}
    if dry_run and not accounts:
        from .postforme import Account
        accounts = {p: Account(f"dry-{p}", p, f"(dry-run {p})", "", "connected", None, True) for p in POSTABLE}

    if not dry_run:
        recover_creating(conn, pfm, campaigns, report)
        collect_results(conn, pfm, report)
        retry_failed(conn, pfm, campaigns, accounts, settings, report)

    slots = upcoming_slots(settings, datetime.now(timezone.utc), set() if dry_run else taken_slots(conn),
                           settings.clips_per_day)
    rotation = list(active)
    for slot in slots:
        produced = False
        for _ in range(len(rotation)):
            campaign = rotation.pop(0)
            rotation.append(campaign)
            try:
                produced = produce_clip(conn, settings, None if dry_run else pfm, campaign, accounts, slot, report)
            except NotAllowedError as exc:
                report.failures.append(f"SAFETY STOP: {exc}")
                return finish(report, conn, campaigns, settings)
            if produced:
                break
        if not produced:
            report.warnings.append(f"No usable material for the {slot.astimezone(settings.timezone):%a %H:%M} slot "
                                   "(add a campaign or new footage)")
    if not active:
        report.warnings.append("No active campaigns in campaigns.yaml")

    try:
        report.shortlist = discover.shortlist(my_platforms)
        seen = {r["url"] for r in conn.execute("SELECT url FROM seen_campaigns")}
        joined = {c.whop_url for c in campaigns.values()}
        report.shortlist = [l for l in report.shortlist if l.url not in seen and l.url not in joined]
        if not dry_run:
            for l in report.shortlist:
                if not l.skip_reason:
                    conn.execute("INSERT OR IGNORE INTO seen_campaigns VALUES (?, ?, ?)", (l.url, l.name, db.now_iso()))
            conn.commit()
    except Exception as exc:  # noqa: BLE001
        report.warnings.append(f"Campaign discovery failed: {exc}")
    return finish(report, conn, campaigns, settings)


def finish(report: RunReport, conn: sqlite3.Connection, campaigns: dict[str, Campaign],
           settings: Settings) -> tuple[RunReport, Path]:
    gather_published(conn, campaigns, report)
    cleanup(settings)
    text = format_report(report, settings)
    path = settings.subdir("reports") / f"{datetime.now(settings.timezone):%Y-%m-%d_%H%M}{'_dry' if report.dry_run else ''}.txt"
    path.write_text(text, encoding="utf-8")
    conn.close()
    return report, path
