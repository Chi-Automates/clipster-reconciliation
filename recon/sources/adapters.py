"""Processor adapters.

Each adapter's only job: pull raw records and hand back canonical Payments.
Fee and FX handling lives here because only the adapter knows its processor's quirks —
Stripe reports fees per charge, PayPal nets them silently, crypto has no fee field at all
but loses value to gas and slippage between send and settle.

These are mocks over realistic payloads so the prototype runs without live credentials.
Swapping in the real API means replacing `_raw()` only.
"""
from __future__ import annotations
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List
from ..models import Payment, Source


def _dt(days_ago: float) -> datetime:
    return datetime(2026, 7, 20) - timedelta(days=days_ago)


class MercuryAdapter:
    """Bank transfers. Clean amounts, no fees, but memos are free-text and unreliable."""
    source = Source.MERCURY

    def _raw(self) -> List[dict]:
        return [
            {"id": "mer_001", "posted": _dt(2), "amount": "4500.00", "ccy": "USD",
             "counterparty": "Telegram Messenger LLP", "description": "INV-2043 campaign q3"},
            {"id": "mer_002", "posted": _dt(4), "amount": "12000.00", "ccy": "USD",
             "counterparty": "UFC Holdings", "description": "payment for invoices 2051 and 2052"},
            {"id": "mer_003", "posted": _dt(9), "amount": "3000.00", "ccy": "USD",
             "counterparty": "Universal Music Grp", "description": "part payment"},
        ]

    def fetch(self) -> List[Payment]:
        out = []
        for r in self._raw():
            amt = Decimal(r["amount"])
            out.append(Payment(
                id=f"mercury:{r['id']}", source=self.source, received_at=r["posted"],
                gross=amt, fee=Decimal("0"), net=amt, currency=r["ccy"],
                payer_name=r["counterparty"], memo=r["description"], raw=r,
            ))
        return out


class StripeAdapter:
    """Card payments. Fee is explicit per charge — net != gross, which breaks naive matching."""
    source = Source.STRIPE

    def _raw(self) -> List[dict]:
        return [
            {"id": "ch_88121", "created": _dt(1), "amount": 250000, "fee": 7550,
             "currency": "usd", "billing_name": "Ed Sheeran Touring Ltd",
             "metadata": {"invoice": "INV-2060"}},
            # fee-adjusted: lands at 1,442.55 against a 1,485.00 invoice
            {"id": "ch_88144", "created": _dt(3), "amount": 148500, "fee": 4245,
             "currency": "usd", "billing_name": "Playboi Carti Merch", "metadata": {}},
        ]

    def fetch(self) -> List[Payment]:
        out = []
        for r in self._raw():
            gross = Decimal(r["amount"]) / 100
            fee = Decimal(r["fee"]) / 100
            out.append(Payment(
                id=f"stripe:{r['id']}", source=self.source, received_at=r["created"],
                gross=gross, fee=fee, net=gross - fee, currency=r["currency"].upper(),
                payer_name=r["billing_name"],
                memo=r.get("metadata", {}).get("invoice", ""), raw=r,
            ))
        return out


class PayPalAdapter:
    """PayPal nets fees silently and payer names are often personal, not the company."""
    source = Source.PAYPAL

    def _raw(self) -> List[dict]:
        return [
            {"txn_id": "8XY22910", "time": _dt(5), "gross": "980.00", "fee": "38.42",
             "ccy": "USD", "payer": "k.lamar.ent@gmail.com", "note": "clipster campaign"},
        ]

    def fetch(self) -> List[Payment]:
        out = []
        for r in self._raw():
            gross, fee = Decimal(r["gross"]), Decimal(r["fee"])
            out.append(Payment(
                id=f"paypal:{r['txn_id']}", source=self.source, received_at=r["time"],
                gross=gross, fee=fee, net=gross - fee, currency=r["ccy"],
                payer_name=r["payer"], memo=r["note"], raw=r,
            ))
        return out


class CryptoAdapter:
    """On-chain. No payer name, no fee field, and value must be fixed at settlement time."""
    source = Source.CRYPTO

    def _raw(self) -> List[dict]:
        return [
            {"tx": "0x9fa2...c41", "ts": _dt(6), "asset": "USDC", "amount": "7500.000000",
             "from": "0xA31c9e...", "usd_rate": "0.9998", "tag": "elton-john-jul"},
        ]

    def fetch(self) -> List[Payment]:
        out = []
        for r in self._raw():
            amt = Decimal(r["amount"])
            out.append(Payment(
                id=f"crypto:{r['tx']}", source=self.source, received_at=r["ts"],
                gross=amt, fee=Decimal("0"), net=amt, currency=r["asset"],
                payer_name=r["from"], memo=r["tag"],
                fx_rate_to_usd=Decimal(r["usd_rate"]), raw=r,
            ))
        return out


ADAPTERS = [MercuryAdapter(), StripeAdapter(), PayPalAdapter(), CryptoAdapter()]


def fetch_all_payments() -> List[Payment]:
    payments = []
    for a in ADAPTERS:
        payments.extend(a.fetch())
    return sorted(payments, key=lambda p: p.received_at)
