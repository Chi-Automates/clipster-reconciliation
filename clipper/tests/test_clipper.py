from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from clipper import db, discover, pipeline, render, selector
from clipper.campaigns import Campaign
from clipper.config import Settings
from clipper.postforme import Account, NotAllowedError, PostForMe, redact

LAGOS = ZoneInfo("Africa/Lagos")


def make_settings(tmp_path: Path, **over) -> Settings:
    base = dict(
        data_dir=tmp_path, campaigns_file=tmp_path / "c.yaml", timezone=LAGOS,
        slots=("08:15", "12:15", "17:15"), clips_per_day=3, min_score=7.0, min_free_gb=0,
        whisper_model="tiny", claude_bin="claude", claude_model=None,
        allowed_account_ids=frozenset({"spc_yt", "spc_ig"}), api_key=None, open_report=False,
        transcript_keep_days=45, max_post_attempts=3,
    )
    base.update(over)
    return Settings(**base)


def make_campaign(**over) -> Campaign:
    base = dict(id="c1", name="Camp", active=True, whop_url="https://w", cpm=1.0,
                platforms=("youtube", "instagram", "x"), sources=(),
                required_text='USE CODE "WHOP"', required_hashtags=("#brand",), banned=("forbidden",))
    base.update(over)
    return Campaign(**base)


TRANSCRIPT = {"segments": [
    {"start": 0.0, "end": 30.0, "text": "a", "words": [{"start": float(i), "end": i + 0.8, "word": f"w{i}"} for i in range(0, 30)]},
    {"start": 30.0, "end": 90.0, "text": "b", "words": [{"start": float(i), "end": i + 0.8, "word": f"w{i}"} for i in range(30, 90)]},
]}


# --------------------------------------------------------------------------- slots
def test_slots_skip_past_and_taken(tmp_path):
    s = make_settings(tmp_path)
    now = datetime(2026, 10, 13, 9, 0, tzinfo=LAGOS).astimezone(timezone.utc)  # after 08:15 Lagos
    taken = {datetime(2026, 10, 13, 12, 15, tzinfo=LAGOS).astimezone(timezone.utc).isoformat(timespec="seconds")}
    slots = [x.astimezone(LAGOS).strftime("%d %H:%M") for x in pipeline.upcoming_slots(s, now, taken, 3)]
    assert slots == ["13 17:15", "14 08:15"]  # 12:15 taken, 14th 12:15 is beyond 24h


def test_first_only_slot_for_youtube_retry(tmp_path):
    s = make_settings(tmp_path)
    now = datetime(2026, 10, 13, 13, 0, tzinfo=LAGOS).astimezone(timezone.utc)
    [slot] = pipeline.upcoming_slots(s, now, set(), 1, first_only=True)
    assert slot.astimezone(LAGOS).strftime("%d %H:%M") == "14 08:15"


# --------------------------------------------------------------------------- selection
def raw(start, end, score=8, title="t"):
    return {"start": start, "end": end, "hook_text": "hook", "title": title, "caption": "cap",
            "hashtags": ["#one", "two"], "hook_score": score, "clarity_score": score,
            "emotion_score": score, "reasoning": "r"}


def test_validate_enforces_length_overlap_score_and_banned():
    camp = make_campaign()
    clips = [raw(0, 25), raw(5, 30), raw(40, 45), raw(50, 80, score=5), raw(60, 85, title="forbidden thing")]
    ok, rejected = selector.validate(clips, TRANSCRIPT, camp, used=[], min_score=7)
    assert [(round(c.start), round(c.end)) for c in ok] == [(0, 25)]
    reasons = " | ".join(rejected)
    assert "overlaps" in reasons and "length" in reasons and "below" in reasons and "banned" in reasons
    assert ok[0].hashtags == ["one", "two"]


def test_validate_respects_already_used_ranges():
    ok, rejected = selector.validate([raw(10, 40)], TRANSCRIPT, make_campaign(), used=[(30, 50)], min_score=7)
    assert not ok and "overlaps" in rejected[0]


def test_caption_always_carries_required_text_and_tags():
    camp = make_campaign()
    yt = selector.build_caption(camp, "Big moment.", ["one"], "youtube")
    assert 'USE CODE "WHOP"' in yt and "#brand" in yt and "#one" in yt
    x = selector.build_caption(camp, "word " * 200, ["one"], "x")
    assert len(x) <= 280 and 'USE CODE "WHOP"' in x


# --------------------------------------------------------------------------- safety
class FakePFM(PostForMe):
    def __init__(self, allowed, accounts):
        super().__init__(None, frozenset(allowed))
        self._accounts = accounts
        self.created: list[dict] = []
        self.remote: dict[str, dict] = {}

    def accounts(self):
        return self._accounts

    def find_by_external_id(self, external_id):
        return self.remote.get(external_id)

    def _request(self, method, path, **kwargs):  # only reached by create_post after the guard
        payload = kwargs["json"]
        post = {"id": f"sp_{len(self.created) + 1}", "external_id": payload["external_id"]}
        self.created.append(payload)
        self.remote[payload["external_id"]] = post
        return post


def acct(i, platform, status="connected"):
    return Account(i, platform, f"user_{platform}", "u", status, None, True)


def test_allowlist_refuses_unlisted_accounts():
    pfm = FakePFM({"spc_yt"}, [acct("spc_yt", "youtube"), acct("spc_fb", "facebook")])
    assert set(pfm.allowed_accounts()) == {"youtube"}
    with pytest.raises(NotAllowedError):
        pfm.create_post({"social_accounts": ["spc_fb"], "external_id": "e"})
    with pytest.raises(NotAllowedError):
        pfm.create_post({"social_accounts": [], "external_id": "e"})
    assert pfm.created == []


def test_empty_allowlist_blocks_everything():
    with pytest.raises(NotAllowedError):
        FakePFM(set(), [acct("spc_yt", "youtube")]).allowed_accounts()


def test_disconnected_allowlisted_account_is_not_used():
    pfm = FakePFM({"spc_yt"}, [acct("spc_yt", "youtube", status="disconnected")])
    assert pfm.allowed_accounts() == {}


def test_redact_strips_tokens_but_keeps_nulls():
    out = redact({"access_token": "secret", "refresh_token": None, "nested": [{"id_token": "x", "ok": 1}]})
    assert out == {"access_token": "<redacted>", "refresh_token": None, "nested": [{"id_token": "<redacted>", "ok": 1}]}


def _seed_clip(conn):
    ts = db.now_iso()
    conn.execute("""INSERT INTO clips (clip_id, campaign_id, video_id, start, end, score, hook_text, title, caption,
                    hashtags, status, media_url, created_at, updated_at)
                    VALUES ('v_1_30', 'c1', 'v', 1, 30, 8, 'h', 'Title', 'Cap', 'one', 'rendered',
                    'https://media/x.mp4', ?, ?)""", (ts, ts))
    conn.commit()
    return conn.execute("SELECT * FROM clips WHERE clip_id = 'v_1_30'").fetchone()


def test_create_post_is_idempotent(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    clip = _seed_clip(conn)
    pfm = FakePFM({"spc_yt"}, [acct("spc_yt", "youtube")])
    camp = make_campaign()
    first = pipeline.create_post_once(conn, pfm, camp, clip, "youtube", "spc_yt", "2026-10-14T07:15:00+00:00", 1)
    second = pipeline.create_post_once(conn, pfm, camp, clip, "youtube", "spc_yt", "2026-10-14T07:15:00+00:00", 1)
    assert first == second and len(pfm.created) == 1
    body = pfm.created[0]
    assert body["platform_configurations"]["youtube"]["privacy_status"] == "public"
    assert 'USE CODE "WHOP"' in body["caption"]


def test_crash_between_create_and_db_write_does_not_double_post(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    clip = _seed_clip(conn)
    pfm = FakePFM({"spc_yt"}, [acct("spc_yt", "youtube")])
    camp = make_campaign()
    # Simulate: row written as 'creating', post created remotely, then the process died.
    pfm.remote["v_1_30.youtube.a1"] = {"id": "sp_remote", "external_id": "v_1_30.youtube.a1"}
    ts = db.now_iso()
    conn.execute("""INSERT INTO posts (clip_id, campaign_id, platform, account_id, attempt, external_id,
                    scheduled_at, status, created_at, updated_at)
                    VALUES ('v_1_30', 'c1', 'youtube', 'spc_yt', 1, 'v_1_30.youtube.a1', 'x', 'creating', ?, ?)""", (ts, ts))
    conn.commit()
    post_id = pipeline.create_post_once(conn, pfm, camp, clip, "youtube", "spc_yt", "x", 1)
    assert post_id == "sp_remote" and pfm.created == []


# --------------------------------------------------------------------------- render & discovery
def test_ass_has_hook_and_word_events_and_escapes_braces():
    words = [{"start": 0.0, "end": 0.4, "word": "{Hello}"}, {"start": 0.5, "end": 0.9, "word": "world."},
             {"start": 2.0, "end": 2.4, "word": "Next"}]
    ass = render.build_ass(words, "Big hook", 3.0, render.style_for("clip-a"))
    events = [l for l in ass.splitlines() if l.startswith("Dialogue:")]
    assert len(events) == 4 and "Hook" in events[0]
    assert "{Hello}" not in ass and "(HELLO)" in ass.upper()


def test_style_varies_between_clips_but_is_stable_per_clip():
    assert render.style_for("a") == render.style_for("a")
    assert len({render.style_for(f"clip{i}") for i in range(10)}) > 1


def test_parse_feed():
    text = ("@ contentrewardsbot · 39m CLIP TRAXNYC & ROMAN SHARFF Budget: $2,000 CPM: $1 per 1,000 views "
            "Platforms: TikTok, Instagram, YouTube Campaign link: https://contentrewards.com/c/campaigns/a5fc2454-9a65 1 2")
    [l] = discover.parse_feed(text)
    assert (l.name, l.cpm, l.budget, l.platforms) == ("CLIP TRAXNYC & ROMAN SHARFF", 1.0, 2000.0,
                                                       ["tiktok", "instagram", "youtube"])
