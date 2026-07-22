"""QuickBooks-side ledger (mocked).

Client names here are the "official" ones. Payments arrive with abbreviations, personal
emails, or wallet addresses — that mismatch is the core matching problem, not an edge case.
"""
from __future__ import annotations
from datetime import date
from decimal import Decimal
from typing import List, Dict
from .models import Invoice


def open_invoices() -> List[Invoice]:
    return [
        Invoice("qb_1", "INV-2043", "Telegram Messenger LLP", Decimal("4500.00"), "USD",
                date(2026, 6, 20), date(2026, 7, 20)),
        Invoice("qb_2", "INV-2051", "UFC Holdings Inc", Decimal("7000.00"), "USD",
                date(2026, 6, 22), date(2026, 7, 22)),
        Invoice("qb_3", "INV-2052", "UFC Holdings Inc", Decimal("5000.00"), "USD",
                date(2026, 6, 22), date(2026, 7, 22)),
        Invoice("qb_4", "INV-2055", "Universal Music Group", Decimal("9000.00"), "USD",
                date(2026, 6, 25), date(2026, 7, 25)),
        Invoice("qb_5", "INV-2060", "Ed Sheeran Touring Limited", Decimal("2500.00"), "USD",
                date(2026, 7, 1), date(2026, 7, 31)),
        Invoice("qb_6", "INV-2061", "Playboi Carti Merchandising", Decimal("1485.00"), "USD",
                date(2026, 7, 2), date(2026, 8, 1)),
        Invoice("qb_7", "INV-2064", "Kendrick Lamar Enterprises", Decimal("980.00"), "USD",
                date(2026, 7, 5), date(2026, 8, 4)),
        Invoice("qb_8", "INV-2066", "Elton John Productions", Decimal("7500.00"), "USD",
                date(2026, 7, 6), date(2026, 8, 5)),
    ]


def apply_payment(invoice: Invoice, amount: Decimal) -> Dict:
    """Stub for the QuickBooks write-back. Real impl: POST a Payment linked to the invoice."""
    invoice.amount_paid += amount
    return {
        "action": "quickbooks.payment.create",
        "invoice": invoice.number,
        "amount": str(amount),
        "invoice_settled": invoice.is_settled,
    }
