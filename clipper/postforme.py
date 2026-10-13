"""Post for Me API client with the allowlist guard.

Every response passes through `redact()` before it leaves this module, because
GET /social-accounts (and post bodies that embed accounts) return raw OAuth tokens.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

log = logging.getLogger(__name__)

BASE_URL = "https://api.postforme.dev/v1"
SECRET_KEYS = {"access_token", "refresh_token", "id_token"}


class NotAllowedError(RuntimeError):
    """Raised when a publish call targets an account outside POSTFORME_ALLOWED_ACCOUNT_IDS."""


def redact(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: ("<redacted>" if k in SECRET_KEYS and v else redact(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact(v) for v in obj]
    return obj


@dataclass(frozen=True)
class Account:
    id: str
    platform: str
    username: str
    user_id: str
    status: str
    access_token_expires_at: str | None
    has_refresh_token: bool


class PostForMe:
    def __init__(self, api_key: str | None, allowed_account_ids: frozenset[str], timeout: int = 60):
        self.allowed = allowed_account_ids
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers["Content-Type"] = "application/json"
        if api_key:  # in Claude's cloud sandbox the proxy injects the Bearer header instead
            self.session.headers["Authorization"] = f"Bearer {api_key}"

    # -- low level -----------------------------------------------------------------
    def _request(self, method: str, path: str, **kwargs) -> Any:
        resp = self.session.request(method, f"{BASE_URL}{path}", timeout=self.timeout, **kwargs)
        if resp.status_code >= 400:
            raise RuntimeError(f"Post for Me {method} {path} -> HTTP {resp.status_code}: {resp.text[:500]}")
        return redact(resp.json()) if resp.content else None

    def _paged(self, path: str, params: dict) -> list[dict]:
        items: list[dict] = []
        offset = 0
        while True:
            body = self._request("GET", path, params={**params, "limit": 100, "offset": offset})
            data = body.get("data", [])
            items.extend(data)
            if not data or not (body.get("meta") or {}).get("next"):
                return items
            offset += len(data)

    # -- accounts ------------------------------------------------------------------
    def accounts(self) -> list[Account]:
        raw = self._request("GET", "/social-accounts", params={"limit": 100})
        return [
            Account(
                id=a["id"], platform=a["platform"], username=a.get("username") or "",
                user_id=a.get("user_id") or "", status=a.get("status") or "",
                access_token_expires_at=a.get("access_token_expires_at"),
                has_refresh_token=a.get("refresh_token") == "<redacted>",
            )
            for a in raw.get("data", [])
        ]

    def allowed_accounts(self) -> dict[str, Account]:
        """platform -> connected, allowlisted account. Raises if the allowlist is empty."""
        if not self.allowed:
            raise NotAllowedError("POSTFORME_ALLOWED_ACCOUNT_IDS is empty; refusing to publish anywhere")
        result: dict[str, Account] = {}
        for acct in self.accounts():
            if acct.id in self.allowed and acct.status == "connected":
                if acct.platform in result:
                    raise NotAllowedError(f"Two allowlisted {acct.platform} accounts; keep exactly one per platform")
                result[acct.platform] = acct
        return result

    def assert_allowed(self, account_ids: list[str]) -> None:
        bad = [a for a in account_ids if a not in self.allowed]
        if bad or not account_ids:
            raise NotAllowedError(f"REFUSED: accounts not in POSTFORME_ALLOWED_ACCOUNT_IDS: {bad or account_ids}")

    # -- media ---------------------------------------------------------------------
    def upload(self, path: Path) -> str:
        urls = self._request("POST", "/media/create-upload-url")
        with path.open("rb") as fh:
            put = requests.put(urls["upload_url"], data=fh, headers={"Content-Type": "video/mp4"}, timeout=600)
        if put.status_code >= 400:
            raise RuntimeError(f"Media upload failed: HTTP {put.status_code} {put.text[:300]}")
        return urls["media_url"]

    # -- posts ---------------------------------------------------------------------
    def find_by_external_id(self, external_id: str) -> dict | None:
        body = self._request("GET", "/social-posts", params={"external_id": external_id, "limit": 10})
        matches = [p for p in body.get("data", []) if p.get("external_id") == external_id]
        return matches[0] if matches else None

    def create_post(self, payload: dict) -> dict:
        self.assert_allowed(list(payload.get("social_accounts", [])))
        return self._request("POST", "/social-posts", json=payload)

    def results_for(self, post_ids: list[str]) -> list[dict]:
        out: list[dict] = []
        for i in range(0, len(post_ids), 20):
            chunk = post_ids[i:i + 20]
            out.extend(self._paged("/social-post-results", {"post_id": chunk}))
        return out

    def post_status(self, post_id: str) -> str | None:
        return (self._request("GET", f"/social-posts/{post_id}") or {}).get("status")


def expiring_accounts(accounts: list[Account], within_days: int = 7) -> list[str]:
    """Accounts that will stop working soon because they have no refresh token."""
    warnings = []
    limit = datetime.now(timezone.utc) + timedelta(days=within_days)
    for a in accounts:
        if a.has_refresh_token or not a.access_token_expires_at:
            continue
        expires = datetime.fromisoformat(a.access_token_expires_at.replace("Z", "+00:00"))
        if expires <= limit:
            warnings.append(f"{a.platform} @{a.username} token expires {expires:%Y-%m-%d}; reconnect it in Post for Me")
    return warnings
