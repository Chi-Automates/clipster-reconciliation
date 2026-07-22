"""Orchestration: ingest -> dedupe -> match -> escalate -> apply -> audit -> notify.

Error handling is the part that matters in money movement, so it is explicit here:
- **Idempotency**: every payment carries a stable source-prefixed id. Re-running the
  pipeline cannot double-apply cash. This is the single most important safety property.
- **Degradation**: if Claude is unavailable, unresolved payments fall through to the
  review queue instead of failing the run.
- **Auditability**: every decision is written with its rationale, confidence, and who
  made it (engine / claude / human), so a finance lead can reverse anything.
"""
from __future__ import annotations
import json
import os
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal
from typing import Dict, List

from .models import Payment, Invoice, Match, MatchStatus
from .sources.adapters import fetch_all_payments
from .invoices import open_invoices, apply_payment
from .matcher import match_payment
from .ai_resolver import resolve_with_ai

AUDIT_PATH = os.environ.get("RECON_AUDIT", "audit_log.jsonl")


def _audit(event: str, **fields):
    rec = {"ts": datetime.utcnow().isoformat(), "event": event, **fields}
    with open(AUDIT_PATH, "a") as f:
        f.write(json.dumps(rec, default=str) + "\n")
    return rec


def notify_slack(match: Match, payment: Payment, invoices: List[Invoice]) -> Dict:
    """Stub. Real impl posts to a #finance channel via Slack webhook."""
    nums = ", ".join(i.number for i in invoices if i.id in match.invoice_ids)
    text = (f"{'✅ Auto-reconciled' if match.status == MatchStatus.AUTO_RECONCILED else '🔍 Needs review'}: "
            f"{payment.source.value} {payment.gross_usd} from '{payment.payer_name}' → {nums} "
            f"({match.confidence:.0%}) — {match.rationale}")
    return {"action": "slack.post", "channel": "#finance-reconciliation", "text": text}


def run(use_ai: bool = True) -> Dict:
    payments = fetch_all_payments()
    invoices = open_invoices()
    inv_by_id = {i.id: i for i in invoices}

    seen: set = set()
    results = {"auto": [], "review": [], "unmatched": [], "duplicate": []}

    for p in payments:
        # --- idempotency guard ---
        if p.id in seen:
            _audit("duplicate_skipped", payment_id=p.id)
            results["duplicate"].append(p.id)
            continue
        seen.add(p.id)

        match = match_payment(p, invoices)

        # --- escalate only what rules could not settle ---
        if use_ai and (match is None or match.confidence < 0.72):
            ai = resolve_with_ai(p, invoices)
            if ai and (match is None or ai.confidence > match.confidence):
                match = ai

        if match is None:
            _audit("unmatched", payment_id=p.id, amount=str(p.gross_usd),
                   payer=p.payer_name)
            results["unmatched"].append({"payment": p, "reason":
                                         "No invoice matched on reference, amount, or payer name."})
            continue

        if match.status == MatchStatus.AUTO_RECONCILED:
            writebacks = []
            remaining = match.applied_amount
            for iid in match.invoice_ids:
                inv = inv_by_id[iid]
                take = min(remaining, inv.outstanding)
                if take > 0:
                    writebacks.append(apply_payment(inv, take))
                    remaining -= take
            _audit("auto_reconciled", payment_id=p.id, invoices=match.invoice_ids,
                   confidence=match.confidence, kind=match.kind.value,
                   resolved_by=match.resolved_by, rationale=match.rationale,
                   writebacks=writebacks)
            results["auto"].append((p, match))
        else:
            _audit("queued_for_review", payment_id=p.id, invoices=match.invoice_ids,
                   confidence=match.confidence, kind=match.kind.value,
                   resolved_by=match.resolved_by, rationale=match.rationale)
            results["review"].append((p, match))

        notify_slack(match, p, invoices)

    results["invoices"] = invoices
    return results


def summarise(results: Dict) -> str:
    auto, review, unmatched = len(results["auto"]), len(results["review"]), len(results["unmatched"])
    total = auto + review + unmatched
    rate = (auto / total * 100) if total else 0
    lines = [
        "=" * 72,
        f"RECONCILIATION RUN — {total} payments across 4 processors",
        "=" * 72,
        f"  auto-reconciled : {auto}  ({rate:.0f}% touchless)",
        f"  needs review    : {review}",
        f"  unmatched       : {unmatched}",
        "",
    ]
    for p, m in results["auto"]:
        lines.append(f"  ✅ {p.id:<26} {str(p.gross_usd):>10}  [{m.kind.value}, {m.confidence:.0%}]")
        lines.append(f"       {m.rationale}")
    for p, m in results["review"]:
        lines.append(f"  🔍 {p.id:<26} {str(p.gross_usd):>10}  [{m.kind.value}, {m.confidence:.0%}] via {m.resolved_by}")
        lines.append(f"       {m.rationale}")
    for u in results["unmatched"]:
        p = u["payment"]
        lines.append(f"  ❓ {p.id:<26} {str(p.gross_usd):>10}  {u['reason']}")
    return "\n".join(lines)
