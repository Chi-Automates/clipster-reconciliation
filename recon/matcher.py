"""Matching engine.

Design: cheap, explainable, deterministic strategies run first and in order of how much
evidence they carry. An LLM is only called for what survives — that keeps cost and latency
low, keeps most decisions auditable, and means a model outage degrades the system to
"more review queue", never to "wrong money moved".

Every strategy returns a rationale string. That is deliberate: a reconciliation a human
cannot audit is worse than no reconciliation, because errors compound silently in the ledger.
"""
from __future__ import annotations
import re
from decimal import Decimal
from itertools import combinations
from typing import List, Optional, Tuple
from rapidfuzz import fuzz

from .models import Payment, Invoice, Match, MatchKind, MatchStatus

# Thresholds. Tuned conservatively: it is far cheaper to review a correct match
# than to silently mis-apply cash in a ledger.
AUTO_THRESHOLD = 0.90
REVIEW_THRESHOLD = 0.55
AMOUNT_TOLERANCE = Decimal("0.02")     # rounding / FX dust
FEE_TOLERANCE_PCT = Decimal("0.05")    # processors rarely exceed ~5%
NAME_MATCH_MIN = 72                    # rapidfuzz token_set_ratio


def extract_invoice_refs(text: str) -> List[str]:
    """Pull invoice numbers out of free-text memos.

    Handles: 'INV-2043', 'inv 2043', 'invoices 2051 and 2052', bare '2060'.
    """
    if not text:
        return []
    t = text.upper()
    refs = set(re.findall(r"INV[-\s]?(\d{3,6})", t))
    # bare 4-digit numbers that look like invoice ids
    refs |= set(re.findall(r"\b(2\d{3})\b", t))
    return sorted(refs)


def _amount_close(a: Decimal, b: Decimal, tol: Decimal = AMOUNT_TOLERANCE) -> bool:
    return abs(a - b) <= tol


def _name_score(payment: Payment, invoice: Invoice) -> int:
    """Fuzzy client-name similarity, with a fallback for emails and wallet addresses."""
    payer = payment.payer_name or ""
    # emails: use the local part, which often carries the artist/company name
    if "@" in payer:
        payer = payer.split("@")[0].replace(".", " ").replace("_", " ")
    # wallet addresses carry no name signal at all
    if payer.startswith("0x"):
        return 0
    return int(fuzz.token_set_ratio(payer.lower(), invoice.client_name.lower()))


def _candidates_by_name(payment: Payment, invoices: List[Invoice]) -> List[Tuple[Invoice, int]]:
    scored = [(inv, _name_score(payment, inv)) for inv in invoices if not inv.is_settled]
    return sorted([s for s in scored if s[1] >= NAME_MATCH_MIN], key=lambda x: -x[1])


# ---------------- strategies, strongest evidence first ----------------

def match_by_reference(payment: Payment, invoices: List[Invoice]) -> Optional[Match]:
    """An explicit invoice number in the memo is the strongest signal available."""
    refs = extract_invoice_refs(f"{payment.memo} {payment.raw.get('description','')}")
    if not refs:
        return None
    hit = [i for i in invoices if not i.is_settled and any(r in i.number for r in refs)]
    if not hit:
        return None

    total = sum(i.outstanding for i in hit)
    amt = payment.gross_usd

    if len(hit) > 1 and _amount_close(amt, total):
        return Match(payment.id, [i.id for i in hit], MatchKind.BUNDLED, 0.97,
                     MatchStatus.AUTO_RECONCILED,
                     f"Memo names invoices {', '.join(i.number for i in hit)}; "
                     f"amount {amt} equals their combined outstanding {total}.",
                     applied_amount=amt)

    inv = hit[0]
    if _amount_close(amt, inv.outstanding):
        return Match(payment.id, [inv.id], MatchKind.EXACT_REF, 0.99,
                     MatchStatus.AUTO_RECONCILED,
                     f"Memo cites {inv.number} and amount matches outstanding exactly.",
                     applied_amount=amt)
    if amt < inv.outstanding:
        return Match(payment.id, [inv.id], MatchKind.PARTIAL, 0.88,
                     MatchStatus.NEEDS_REVIEW,
                     f"Memo cites {inv.number} but {amt} is less than outstanding "
                     f"{inv.outstanding} — looks like a partial payment.",
                     applied_amount=amt)
    return Match(payment.id, [inv.id], MatchKind.EXACT_REF, 0.60,
                 MatchStatus.NEEDS_REVIEW,
                 f"Memo cites {inv.number} but amount {amt} exceeds outstanding "
                 f"{inv.outstanding} — possible overpayment or credit.",
                 applied_amount=inv.outstanding)


def match_fee_adjusted(payment: Payment, invoices: List[Invoice]) -> Optional[Match]:
    """Stripe/PayPal deduct fees, so what landed never equals the invoice.

    Matching net-against-invoice is the classic false negative in naive reconcilers.
    """
    if payment.fee <= 0:
        return None
    for inv, score in _candidates_by_name(payment, invoices):
        if _amount_close(payment.gross_usd, inv.outstanding):
            fee_pct = (payment.fee / payment.gross) if payment.gross else Decimal("0")
            if fee_pct <= FEE_TOLERANCE_PCT:
                return Match(payment.id, [inv.id], MatchKind.FEE_ADJUSTED, 0.94,
                             MatchStatus.AUTO_RECONCILED,
                             f"Gross {payment.gross_usd} matches {inv.number}; "
                             f"{payment.fee} processor fee explains the shortfall in net "
                             f"({payment.net_usd}). Name similarity {score}%.",
                             applied_amount=payment.gross_usd)
    return None


def match_by_amount_and_name(payment: Payment, invoices: List[Invoice]) -> Optional[Match]:
    """No reference, but the client name and amount agree."""
    for inv, score in _candidates_by_name(payment, invoices):
        if _amount_close(payment.gross_usd, inv.outstanding):
            conf = 0.93 if score >= 90 else 0.80
            status = MatchStatus.AUTO_RECONCILED if conf >= AUTO_THRESHOLD else MatchStatus.NEEDS_REVIEW
            return Match(payment.id, [inv.id], MatchKind.AMOUNT_DATE, conf, status,
                         f"Amount {payment.gross_usd} matches {inv.number} outstanding; "
                         f"payer '{payment.payer_name}' ~ '{inv.client_name}' ({score}%).",
                         applied_amount=payment.gross_usd)
    return None


def match_bundled(payment: Payment, invoices: List[Invoice]) -> Optional[Match]:
    """One payment settling several invoices for the same client."""
    cands = [i for i, _ in _candidates_by_name(payment, invoices)]
    amt = payment.gross_usd
    for n in (2, 3):
        for combo in combinations(cands, n):
            if _amount_close(sum(i.outstanding for i in combo), amt):
                return Match(payment.id, [i.id for i in combo], MatchKind.BUNDLED, 0.86,
                             MatchStatus.NEEDS_REVIEW,
                             f"{amt} equals the combined outstanding of "
                             f"{', '.join(i.number for i in combo)} for this client.",
                             applied_amount=amt)
    return None


def match_partial(payment: Payment, invoices: List[Invoice]) -> Optional[Match]:
    """Instalment against a larger open invoice."""
    for inv, score in _candidates_by_name(payment, invoices):
        if payment.gross_usd < inv.outstanding:
            return Match(payment.id, [inv.id], MatchKind.PARTIAL, 0.72,
                         MatchStatus.NEEDS_REVIEW,
                         f"{payment.gross_usd} is less than {inv.number} outstanding "
                         f"{inv.outstanding}; payer name matches {score}%. Likely instalment.",
                         applied_amount=payment.gross_usd)
    return None


STRATEGIES = [
    match_by_reference,
    match_fee_adjusted,
    match_by_amount_and_name,
    match_bundled,
    match_partial,
]


def match_payment(payment: Payment, invoices: List[Invoice]) -> Optional[Match]:
    """Run strategies in order; first confident answer wins."""
    best: Optional[Match] = None
    for strategy in STRATEGIES:
        m = strategy(payment, invoices)
        if m and (best is None or m.confidence > best.confidence):
            best = m
            if best.confidence >= AUTO_THRESHOLD:
                break
    return best
