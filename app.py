"""Reconciliation review dashboard.

The queue is the product. Auto-reconciliation is only trustworthy if the cases the system
is unsure about land somewhere a human can settle them in seconds — with the reasoning
visible, not hidden behind a score.
"""
import os
import streamlit as st
from recon.pipeline import run
from recon.models import MatchStatus

st.set_page_config(page_title="Clipster Reconciliation", page_icon="💸", layout="wide")
st.title("💸 Payment & Invoice Reconciliation")
st.caption("Mercury · PayPal · Stripe · Crypto → QuickBooks. Rules settle the clear cases; "
           "Claude resolves ambiguous identity; humans confirm the rest.")

from recon.ai_resolver import _get_key
has_key = bool(_get_key())
use_ai = st.sidebar.toggle("Use Claude for ambiguous cases", value=has_key)
if not has_key:
    st.sidebar.warning("No ANTHROPIC_API_KEY — deterministic engine only.")

if st.sidebar.button("▶ Run reconciliation", use_container_width=True):
    st.session_state.results = run(use_ai=use_ai)

res = st.session_state.get("results")
if not res:
    st.info("Run a reconciliation to populate the queue.")
    st.stop()

total = len(res["auto"]) + len(res["review"]) + len(res["unmatched"])
c1, c2, c3, c4 = st.columns(4)
c1.metric("Payments", total)
c2.metric("Auto-reconciled", len(res["auto"]),
          f"{len(res['auto'])/total*100:.0f}% touchless" if total else "")
c3.metric("Needs review", len(res["review"]))
c4.metric("Unmatched", len(res["unmatched"]))

st.subheader("🔍 Review queue")
if not res["review"] and not res["unmatched"]:
    st.success("Queue is clear.")

for p, m in res["review"]:
    with st.container(border=True):
        a, b = st.columns([3, 1])
        a.markdown(f"**{p.payer_name}** · `{p.source.value}` · **${p.gross_usd}**")
        a.caption(f"{m.kind.value} · resolved by {m.resolved_by} · {m.rationale}")
        b.progress(m.confidence, text=f"{m.confidence:.0%}")
        x, y, z = b.columns(3)
        x.button("✓", key=f"ok{p.id}", help="Confirm and post to QuickBooks")
        y.button("✎", key=f"ed{p.id}", help="Reassign invoice")
        z.button("✕", key=f"no{p.id}", help="Reject")

for u in res["unmatched"]:
    p = u["payment"]
    with st.container(border=True):
        st.markdown(f"**{p.payer_name}** · `{p.source.value}` · **${p.gross_usd}** — ❓ unmatched")
        st.caption(f"{u['reason']}  Memo: _{p.memo or '—'}_")

with st.expander(f"✅ Auto-reconciled ({len(res['auto'])})"):
    for p, m in res["auto"]:
        st.markdown(f"- **${p.gross_usd}** {p.payer_name} → `{m.kind.value}` "
                    f"({m.confidence:.0%}) — {m.rationale}")

with st.expander("📒 Invoice ledger after run"):
    for i in res["invoices"]:
        state = "settled" if i.is_settled else f"outstanding ${i.outstanding}"
        st.markdown(f"- `{i.number}` {i.client_name} — ${i.amount_due} → **{state}**")
