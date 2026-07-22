"""Canonical models.

Design note: the first real decision in this system is refusing to work in each
processor's native shape. Mercury, PayPal, Stripe and on-chain transfers disagree on
field names, fee handling, currency, and what "amount" even means. Everything is
normalised into one Payment shape at the edge, so the matching engine never has to
know where money came from. New processors become one adapter, not a rewrite.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime, date
from decimal import Decimal
from enum import Enum
from typing import Optional, List


class Source(str, Enum):
    MERCURY = "mercury"
    PAYPAL = "paypal"
    STRIPE = "stripe"
    CRYPTO = "crypto"


class MatchStatus(str, Enum):
    AUTO_RECONCILED = "auto_reconciled"   # high confidence, written back
    NEEDS_REVIEW = "needs_review"         # ambiguous, queued for a human
    UNMATCHED = "unmatched"               # no plausible candidate
    DUPLICATE = "duplicate"               # already ingested


class MatchKind(str, Enum):
    EXACT_REF = "exact_reference"
    AMOUNT_DATE = "amount_and_date"
    FEE_ADJUSTED = "fee_adjusted"
    PARTIAL = "partial_payment"
    BUNDLED = "bundled_payment"
    AI_RESOLVED = "ai_resolved"


@dataclass
class Payment:
    """A payment normalised from any processor."""
    id: str                       # stable, source-prefixed: idempotency key
    source: Source
    received_at: datetime
    gross: Decimal                # what the customer sent
    fee: Decimal                  # what the processor took
    net: Decimal                  # what actually landed
    currency: str
    payer_name: str               # often messy / abbreviated
    memo: str = ""                # free text: may hold an invoice ref
    raw: dict = field(default_factory=dict)

    # FX: crypto and foreign payments settle at a rate we must record, not infer later
    fx_rate_to_usd: Decimal = Decimal("1")

    @property
    def gross_usd(self) -> Decimal:
        return (self.gross * self.fx_rate_to_usd).quantize(Decimal("0.01"))

    @property
    def net_usd(self) -> Decimal:
        return (self.net * self.fx_rate_to_usd).quantize(Decimal("0.01"))


@dataclass
class Invoice:
    """An open invoice from QuickBooks."""
    id: str
    number: str                   # e.g. INV-2043
    client_name: str
    amount_due: Decimal
    currency: str
    issued_on: date
    due_on: date
    amount_paid: Decimal = Decimal("0")

    @property
    def outstanding(self) -> Decimal:
        return self.amount_due - self.amount_paid

    @property
    def is_settled(self) -> bool:
        return self.outstanding <= Decimal("0.01")


@dataclass
class Match:
    """A proposed or confirmed reconciliation."""
    payment_id: str
    invoice_ids: List[str]
    kind: MatchKind
    confidence: float             # 0..1
    status: MatchStatus
    rationale: str                # human-readable WHY - shown in the review queue
    applied_amount: Decimal = Decimal("0")
    resolved_by: str = "engine"   # engine | claude | human

    def to_dict(self):
        d = asdict(self)
        d["applied_amount"] = str(self.applied_amount)
        return d
