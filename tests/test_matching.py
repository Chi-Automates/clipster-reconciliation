"""Edge-case tests. These encode the failure modes that make reconciliation hard."""
from decimal import Decimal
from datetime import datetime
from recon.models import Payment, Source, MatchKind, MatchStatus
from recon.invoices import open_invoices
from recon.matcher import (match_payment, extract_invoice_refs,
                           match_fee_adjusted, AUTO_THRESHOLD)


def _p(**kw):
    base = dict(id="t:1", source=Source.MERCURY, received_at=datetime(2026, 7, 18),
                gross=Decimal("100"), fee=Decimal("0"), net=Decimal("100"),
                currency="USD", payer_name="Test", memo="")
    base.update(kw)
    base["net"] = base["gross"] - base["fee"]
    return Payment(**base)


def test_reference_extraction_variants():
    assert "2043" in extract_invoice_refs("INV-2043 campaign")
    assert "2043" in extract_invoice_refs("inv 2043")
    refs = extract_invoice_refs("payment for invoices 2051 and 2052")
    assert "2051" in refs and "2052" in refs
    assert extract_invoice_refs("") == []


def test_exact_reference_auto_reconciles():
    m = match_payment(_p(gross=Decimal("4500.00"), memo="INV-2043",
                         payer_name="Telegram Messenger LLP"), open_invoices())
    assert m.kind == MatchKind.EXACT_REF
    assert m.status == MatchStatus.AUTO_RECONCILED


def test_bundled_payment_from_memo():
    m = match_payment(_p(gross=Decimal("12000.00"), payer_name="UFC Holdings",
                         memo="payment for invoices 2051 and 2052"), open_invoices())
    assert m.kind == MatchKind.BUNDLED
    assert len(m.invoice_ids) == 2


def test_processor_fee_does_not_break_match():
    """The classic false negative: net != invoice, but gross does."""
    p = _p(source=Source.STRIPE, gross=Decimal("1485.00"), fee=Decimal("42.45"),
           payer_name="Playboi Carti Merch")
    m = match_fee_adjusted(p, open_invoices())
    assert m is not None and m.kind == MatchKind.FEE_ADJUSTED
    assert m.confidence >= AUTO_THRESHOLD


def test_partial_payment_is_reviewed_not_auto_applied():
    m = match_payment(_p(gross=Decimal("3000.00"), payer_name="Universal Music Grp",
                         memo="part payment"), open_invoices())
    assert m.kind == MatchKind.PARTIAL
    assert m.status == MatchStatus.NEEDS_REVIEW


def test_overpayment_is_flagged_not_silently_applied():
    m = match_payment(_p(gross=Decimal("9999.00"), memo="INV-2043",
                         payer_name="Telegram Messenger LLP"), open_invoices())
    assert m.status == MatchStatus.NEEDS_REVIEW


def test_wallet_address_yields_no_name_signal():
    """Crypto has no payer identity - must not fuzzy-match to a random client."""
    m = match_payment(_p(source=Source.CRYPTO, gross=Decimal("7500.00"),
                         payer_name="0xA31c9e...", memo="elton-john-jul"), open_invoices())
    assert m is None


def test_fx_conversion_applied():
    p = _p(source=Source.CRYPTO, gross=Decimal("7500.000000"),
           fx_rate_to_usd=Decimal("0.9998"))
    assert p.gross_usd == Decimal("7498.50")
