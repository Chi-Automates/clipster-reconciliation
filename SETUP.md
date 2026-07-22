# SETUP — start here

Everything below is copy-paste. Windows PowerShell commands first (your setup), Mac/Linux noted where different.

---

## What this actually is

A Python program that solves Clipster's Option 2 (payment reconciliation). It has three parts:

| Part | File(s) | What it does |
|---|---|---|
| **The engine** | `recon/` | Pulls payments from 4 fake processors, matches them to invoices, decides what to auto-apply vs. send to a human |
| **The CLI demo** | `run_demo.py` | Runs the engine once and prints the result to your terminal — this is your video demo |
| **The dashboard** | `app.py` | A web UI showing the review queue — this is your hosted demo link |

Nothing connects to real Mercury/Stripe/QuickBooks. The data is realistic mock data, which the brief explicitly allows ("a mocked project environment").

---

## STEP 1 — Unzip and open a terminal there

Unzip `clipster-reconciliation.zip`. You'll get a folder called `pkg` — **rename it** to `clipster-reconciliation`.

Open PowerShell and go into it:

```powershell
cd C:\Users\HomePC\Desktop\clipster-reconciliation
```

Check you're in the right place — this should list `recon`, `app.py`, `run_demo.py`:

```powershell
dir
```

---

## STEP 2 — Install dependencies

```powershell
pip install -r requirements.txt
```

Takes about a minute. If `pip` isn't recognised, use `python -m pip install -r requirements.txt`.

---

## STEP 3 — Run it (no API key needed yet)

```powershell
python run_demo.py --no-ai
```

**You should see:** a run summary — 7 payments, 4 auto-reconciled (57% touchless), 1 needing review, 2 unmatched. If you see that, the engine works.

The 2 unmatched are the crypto wallet and the PayPal Gmail. That's intentional — rules can't solve identity. That's what the AI step is for.

---

## STEP 4 — Run the tests

```powershell
python -m pytest tests/ -q
```

**You should see:** `8 passed`. Mention this in your video — it shows you tested the edge cases.

---

## STEP 5 — Add your API key and run the AI step

Get your key from console.anthropic.com. Then in PowerShell:

```powershell
$env:ANTHROPIC_API_KEY = "sk-ant-your-actual-key-here"
python run_demo.py
```

*(Mac/Linux: `export ANTHROPIC_API_KEY="sk-ant-..."`)*

**You should now see** the 2 previously-unmatched payments resolved by Claude — the wallet address matched to Elton John Productions, the Gmail matched to Kendrick Lamar Enterprises. **This is your money shot for the video.**

⚠️ That `$env:` line only lasts for that PowerShell window. Open a new window, set it again.

---

## STEP 6 — Run the dashboard

```powershell
streamlit run app.py
```

Your browser opens automatically. Click **▶ Run reconciliation** in the sidebar. You'll see the metrics, the review queue with confidence bars, and expandable sections.

Press `Ctrl+C` in PowerShell to stop it.

---

## STEP 7 — Push to GitHub

Make it **public** — they need to see it.

```powershell
git init
git add -A
git commit -m "Payment and invoice reconciliation system"
```

Then create the repo. If you have GitHub CLI:

```powershell
gh repo create clipster-reconciliation --public --source=. --push
```

If not, create it manually at github.com/new (name: `clipster-reconciliation`, public, don't add a README), then:

```powershell
git remote add origin https://github.com/Chi-Automates/clipster-reconciliation.git
git branch -M main
git push -u origin main
```

✅ **Your `.gitignore` already excludes `.env` and `audit_log.jsonl`** — your API key will not be pushed. Verify with `git status` before pushing that no `.env` appears.

---

## STEP 8 — Deploy the live demo (free, ~5 minutes)

Streamlit Community Cloud is the fastest path and it's free.

1. Go to **share.streamlit.io** and sign in with GitHub
2. Click **New app**
3. Repository: `Chi-Automates/clipster-reconciliation` · Branch: `main` · Main file path: `app.py`
4. Before clicking Deploy, open **Advanced settings → Secrets** and paste:

```toml
ANTHROPIC_API_KEY = "sk-ant-your-actual-key-here"
```

5. Click **Deploy**

You'll get a URL like `https://clipster-reconciliation.streamlit.app`. That's your hosted demo link for submission.

⚠️ **Cost warning:** a public app with your API key means anyone who finds it can trigger Claude calls on your account. For a hiring demo that's low risk, but set a spend limit in the Anthropic console, and delete the app after they've reviewed it.

*(Prefer zero risk? Deploy without the secret. The dashboard still runs the deterministic engine and shows 57% touchless — and you demo the AI step in the video instead.)*

---

## STEP 9 — Record the video (5 minutes)

Loom or OBS. Suggested flow:

1. **(45s) The problem.** Not data movement — deciding what a payment is *for*. Name the five things that break naive matching: processor fees, partial payments, bundled payments, FX, and payer identity.
2. **(60s) The architecture.** Rules first, model second. Why: rules are cheap, instant, explainable, and settle most volume — Claude is called only where it's genuinely better, at reading messy human identity. If Claude is down, the system degrades to a longer review queue, never to wrong money moved.
3. **(90s) Run it.** `python run_demo.py --no-ai` → point at the bundled UFC match and the fee-adjusted Stripe charge → point at the 2 unmatched and say why rules can't solve them → set the key, rerun, show Claude resolving both.
4. **(45s) The dashboard.** Show the review queue — every decision carries its reasoning, because a reconciliation a human can't audit is worse than none.
5. **(30s) Safety.** Idempotency (can't double-apply cash), overpayment guard, full audit log, 8 tests.
6. **(30s) With real data.** Learn from the review queue — every human correction becomes a client-alias entry, so today's Claude call is tomorrow's deterministic hit, and the touchless rate climbs on its own.

**Speak to the decisions, not the code.** They said they're evaluating how you define the problem.

---

## STEP 10 — Submit

Their form asks for three things:

1. **Working prototype** → the GitHub repo
2. **Video walkthrough** → your Loom link
3. **Project link** → the Streamlit URL (or the repo again)

Plus they asked you to briefly mention:

> **Tools and AI models used:** Python, rapidfuzz for name similarity, Streamlit for the review UI, Claude Sonnet via the Anthropic API for ambiguous-identity resolution. Built using Claude Code, which is also how I work day to day.
>
> **What I'd improve with access to real systems and data:** swap the mock adapters for live Mercury/Stripe/PayPal/QuickBooks APIs (the canonical model means each is one file); learn from the review queue so confirmed matches build a client-alias table and today's model call becomes tomorrow's deterministic hit; tune the confidence thresholds against real precision data instead of my estimates; push approve/reassign into Slack; and handle refunds, chargebacks, credit notes and multi-currency invoices.

---

## If something breaks

| Problem | Fix |
|---|---|
| `python` not recognised | Install Python 3.10+ from python.org, tick "Add to PATH" |
| `ModuleNotFoundError` | You're in the wrong folder, or skipped Step 2 |
| `streamlit` not recognised | `python -m streamlit run app.py` |
| AI step does nothing | Key not set in *this* terminal window — redo Step 5 |
| Deployed app can't find key | Streamlit Cloud → your app → Settings → Secrets |
