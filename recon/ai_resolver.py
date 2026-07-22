"""Claude-backed resolver for the residue.

Only payments the deterministic engine could not settle reach this. That is the point:
the LLM is used where it is genuinely better than rules — reading intent out of messy
human text, recognising that 'k.lamar.ent@gmail.com' is Kendrick Lamar Enterprises, or
that 'elton-john-jul' tags an Elton John invoice — and nowhere else.

It never writes to the ledger directly. It proposes, with a confidence and a reason, and
anything below the auto threshold still lands in the human review queue.
"""
from __future__ import annotations
import json
import os
from decimal import Decimal
from typing import List, Optional

from .models import Payment, Invoice, Match, MatchKind, MatchStatus
from .matcher import AUTO_THRESHOLD

SYSTEM = """You reconcile incoming payments against open invoices.
You are given ONE payment and a list of candidate open invoices.
Decide which invoice(s) the payment settles, if any.

Rules:
- Only choose invoices from the provided list. Never invent an invoice.
- Payer identity may be an email, a wallet address, an abbreviation, or a tag. Reason about it.
- The amount may differ from the invoice due to processor fees, FX, partial payment, or bundling.
- If genuinely unsure, say so with low confidence. A wrong reconciliation is worse than none.

Return JSON only:
{"invoice_ids": ["..."], "confidence": 0.0-1.0, "kind": "exact|partial|bundled|none",
 "rationale": "one or two sentences a finance person can audit"}"""


def _get_key() -> str | None:
    """Read the key from env (local) or Streamlit secrets (deployed)."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key
    try:
        import streamlit as st
        return st.secrets.get("ANTHROPIC_API_KEY")
    except Exception:
        return None


def _client():
    key = _get_key()
    if not key:
        return None
    try:
        import anthropic
        return anthropic.Anthropic(api_key=key)
    except ImportError:
        return None


def resolve_with_ai(payment: Payment, invoices: List[Invoice]) -> Optional[Match]:
    client = _client()
    open_inv = [i for i in invoices if not i.is_settled]
    if not client or not open_inv:
        return None

    payload = {
        "payment": {
            "source": payment.source.value,
            "received_at": payment.received_at.isoformat(),
            "gross_usd": str(payment.gross_usd),
            "net_usd": str(payment.net_usd),
            "fee": str(payment.fee),
            "currency": payment.currency,
            "payer_name": payment.payer_name,
            "memo": payment.memo,
        },
        "candidate_invoices": [
            {"id": i.id, "number": i.number, "client": i.client_name,
             "outstanding": str(i.outstanding), "due_on": i.due_on.isoformat()}
            for i in open_inv
        ],
    }

    try:
        msg = client.messages.create(
            model=os.environ.get("RECON_MODEL", "claude-sonnet-4-6"),
            max_tokens=600,
            system=SYSTEM,
            messages=[{"role": "user", "content": json.dumps(payload, indent=2)}],
        )
        raw = "".join(b.text for b in msg.content if b.type == "text")
        raw = raw.replace("```json", "").replace("```", "").strip()
        data = json.loads(raw)
    except Exception as e:
        print(f"[ai_resolver] {payment.id}: {e}")
        return None

    ids = data.get("invoice_ids") or []
    if not ids or data.get("kind") == "none":
        return None

    conf = float(data.get("confidence", 0))
    chosen = [i for i in open_inv if i.id in ids]
    if not chosen:
        return None

    applied = min(payment.gross_usd, sum(i.outstanding for i in chosen))
    # Claude proposes; it does not get to auto-apply on thin confidence.
    status = MatchStatus.AUTO_RECONCILED if conf >= AUTO_THRESHOLD else MatchStatus.NEEDS_REVIEW

    return Match(payment.id, ids, MatchKind.AI_RESOLVED, conf, status,
                 data.get("rationale", "Resolved by model."),
                 applied_amount=Decimal(applied), resolved_by="claude")
