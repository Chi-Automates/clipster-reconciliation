# Payment & Invoice Reconciliation — Clipster Application Task

**Option 2.** Payments arrive via Mercury, PayPal, Stripe and crypto; invoices live in
QuickBooks. Matching them is manual. This is a working prototype of a system that does it.

---

## How I framed the problem

The brief says it isn't a data-movement task, and it isn't. Moving payments into QuickBooks
is trivial. The actual problem is **deciding what a payment is for when the evidence is
incomplete** — and doing it without silently corrupting the ledger.

Reconciliation is hard for five specific reasons, and a system that ignores any of them
produces confident, wrong answers:

| Failure mode | Why naive matching breaks |
|---|---|
| **Processor fees** | Stripe/PayPal deduct before settlement. Net never equals the invoice. |
| **Partial payments** | One invoice, several instalments. Amount alone proves nothing. |
| **Bundled payments** | One transfer settling several invoices at once. |
| **FX / crypto** | Value must be fixed at settlement, not inferred later. |
| **Identity** | Payer is `k.lamar.ent@gmail.com` or `0xA31c9e…`, not "Kendrick Lamar Enterprises". |

So the design goal isn't "match more". It's **maximise touchless reconciliation while making
every remaining decision fast and auditable for a human** — and never auto-apply cash on
weak evidence. A wrong reconciliation is more expensive than an unreconciled one, because
the error compounds quietly.

## Architecture

```
Mercury ─┐
PayPal  ─┤→ adapters → canonical Payment → dedupe (idempotency)
Stripe  ─┤                                      │
Crypto  ─┘                                      ▼
                                   deterministic engine (5 strategies)
                                                │
                              confident? ────────┴──────── ambiguous?
                                   │                            │
                              auto-apply                   Claude resolver
                              → QuickBooks                      │
                              → Slack                     confident? → apply
                              → audit log                 unsure?   → review queue
```

**Why rules first, model second.** Deterministic strategies are cheap, instant, and
explainable, and they settle most volume. Claude is called only on the residue — where it's
genuinely better than rules, at reading intent out of messy human text. That keeps cost and
latency down, keeps most decisions auditable, and means a model outage degrades the system
to "a longer review queue", never to "wrong money moved".

**Strategies, in order of evidence strength:** explicit invoice reference in the memo →
fee-adjusted amount → amount + fuzzy payer name → bundled combinations → partial payment.
First confident answer wins.

**Confidence tiers.** ≥0.90 auto-applies. 0.55–0.90 goes to the review queue with its
reasoning attached. Below that, unmatched. Thresholds are deliberately conservative.

## Results on the sample data

7 payments across 4 processors, 8 open invoices:

- **4 auto-reconciled (57% touchless)** — including a bundled Mercury transfer settling two
  UFC invoices, and a Stripe charge where the $42.45 fee would have defeated naive matching.
- **1 queued** — a $3,000 payment against a $9,000 Universal Music invoice, correctly
  identified as a partial payment rather than force-matched.
- **2 escalated to Claude** — a crypto payment whose only identity is a wallet address plus
  the tag `elton-john-jul`, and a PayPal payment from a personal Gmail address. Neither is
  solvable by rules; both are straightforward for a model reasoning over candidate invoices.

That split is the whole thesis: rules where rules work, a model only where they can't.

## Error handling

- **Idempotency** — every payment carries a stable source-prefixed ID. Re-running cannot
  double-apply cash. This is the most important safety property in the system.
- **Graceful degradation** — no API key or a model failure sends payments to the review
  queue, not to a crash or a guess.
- **Overpayment guard** — an amount exceeding the outstanding balance is flagged, never
  silently applied.
- **No identity, no fuzzy match** — wallet addresses deliberately score zero on name
  similarity so they can't be matched to an unrelated client by coincidence.
- **Full audit trail** — `audit_log.jsonl` records every decision with rationale, confidence
  and who made it (engine / claude / human), so finance can reverse anything.

Eight tests encode these as regressions (`pytest tests/`).

## Run it

```bash
pip install -r requirements.txt
python run_demo.py --no-ai        # deterministic engine only
export ANTHROPIC_API_KEY=sk-ant-…
python run_demo.py                # with Claude resolving ambiguous identity
streamlit run app.py              # review dashboard
pytest tests/ -q
```

## Tools and models used

Python, `rapidfuzz` for name similarity, Streamlit for the review UI, **Claude (Sonnet)** via
the Anthropic API for ambiguous-identity resolution. I used Claude Code throughout to build
it — which is also how I work day to day.

## What I'd do with access to real systems and data

1. **Replace mocks with live adapters** — Mercury, Stripe, PayPal and QuickBooks APIs are
   all straightforward; the canonical model means each is one file, and nothing downstream
   changes.
2. **Learn from the review queue.** Every human correction is labelled training signal. I'd
   store confirmed matches and use them to build a client-alias table (`k.lamar.ent@gmail.com`
   → Kendrick Lamar Enterprises, wallet → client), so today's Claude call becomes tomorrow's
   deterministic hit. The touchless rate should climb on its own.
3. **Tune thresholds on your actual data** rather than my guesses — measure precision at each
   confidence band and set the auto-apply line where false positives approach zero.
4. **Close the loop into Slack** — approve or reassign from the message itself, so finance
   never opens another tool.
5. **Handle the messier realities I mocked past**: refunds and chargebacks, multi-currency
   invoices, credit notes, and duplicate invoice numbers across periods.

The prototype deliberately stops short of a polished production system — the brief asked for
thoughtful and functional over large and superficial, and the interesting work here is the
matching logic and the safety model, not the plumbing.
