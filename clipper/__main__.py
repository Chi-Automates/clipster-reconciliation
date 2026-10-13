"""CLI: python -m clipper <command>

  daily [--dry-run]   full run: results, retries, new clips, scheduling, report
  check               verify Post for Me accounts against the allowlist (read-only)
  discover            list live Whop campaigns that fit your accounts (read-only)
  links [--days N]    print published post URLs for Whop submission
"""
from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from logging.handlers import RotatingFileHandler

from . import db, discover
from .config import load_settings
from .pipeline import run_daily
from .postforme import NotAllowedError, PostForMe


def setup_logging(log_dir) -> None:
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    file = RotatingFileHandler(log_dir / "clipper.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    file.setFormatter(fmt)
    root.addHandler(console)
    root.addHandler(file)
    for noisy in ("urllib3", "faster_whisper", "httpx", "httpx2", "huggingface_hub"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def open_file(path) -> None:
    try:
        if sys.platform == "win32":
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", str(path)], check=False)
    except OSError:
        pass


def cmd_daily(args) -> int:
    settings = load_settings()
    setup_logging(settings.subdir("logs"))
    try:
        report, path = run_daily(settings, dry_run=args.dry_run)
    except NotAllowedError as exc:
        print(f"SAFETY STOP: {exc}")
        return 2
    print(path.read_text(encoding="utf-8"))
    print(f"Report saved to {path}")
    if settings.open_report and (report.published or report.failures or args.dry_run):
        open_file(path)
    return 1 if report.failures else 0


def cmd_check(_args) -> int:
    settings = load_settings()
    pfm = PostForMe(settings.api_key, settings.allowed_account_ids)
    accounts = pfm.accounts()
    print(f"Allowlist: {', '.join(sorted(settings.allowed_account_ids)) or '(EMPTY - publishing disabled)'}\n")
    for a in accounts:
        flag = "ALLOWED" if a.id in settings.allowed_account_ids else "ignored"
        print(f"  [{flag:7}] {a.platform:9} {a.username:28} {a.status:12} {a.id}")
    missing = settings.allowed_account_ids - {a.id for a in accounts}
    if missing:
        print(f"\nWARNING: allowlisted IDs not found in Post for Me: {', '.join(sorted(missing))}")
    try:
        usable = pfm.allowed_accounts()
        print(f"\nWill post to: {', '.join(f'{p} @{a.username}' for p, a in usable.items()) or 'nothing'}")
    except NotAllowedError as exc:
        print(f"\nSAFETY: {exc}")
        return 2
    return 0


def cmd_discover(_args) -> int:
    settings = load_settings()
    try:
        mine = set(PostForMe(settings.api_key, settings.allowed_account_ids).allowed_accounts())
    except Exception:  # noqa: BLE001
        mine = {"youtube", "instagram", "x"}
    for l in discover.shortlist(mine):
        status = f"SKIP ({l.skip_reason})" if l.skip_reason else "FITS"
        print(f"{status:60} ${l.cpm}/1K  ${l.budget:,.0f}  {'/'.join(l.platforms)}  {l.name}\n    {l.url}")
        if l.description and not l.skip_reason:
            print(f"    {l.description[:220]}")
    return 0


def cmd_links(args) -> int:
    settings = load_settings()
    conn = db.connect(settings.db_path)
    since = (datetime.now(timezone.utc) - timedelta(days=args.days)).isoformat(timespec="seconds")
    rows = conn.execute(
        "SELECT campaign_id, platform, url, scheduled_at FROM posts WHERE status = 'published' AND scheduled_at >= ? "
        "ORDER BY campaign_id, scheduled_at", (since,)).fetchall()
    current = None
    for r in rows:
        if r["campaign_id"] != current:
            current = r["campaign_id"]
            print(f"\n{current}")
        print(f"  {r['platform']:9} {r['url']}")
    if not rows:
        print("No published posts in that window.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="clipper")
    sub = parser.add_subparsers(dest="command", required=True)
    daily = sub.add_parser("daily")
    daily.add_argument("--dry-run", action="store_true", help="do everything except upload and publish")
    daily.set_defaults(func=cmd_daily)
    sub.add_parser("check").set_defaults(func=cmd_check)
    sub.add_parser("discover").set_defaults(func=cmd_discover)
    links = sub.add_parser("links")
    links.add_argument("--days", type=int, default=2)
    links.set_defaults(func=cmd_links)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
