# Nightshift

**Bitget AI Hackathon S2 · Agentic Trading · Cross-Asset Execution**

One Bitget UTA. Frozen NVIDIA (`rNVDA`) collateral. Bitcoin still moves. Monday can kill the account. Nightshift prices **Monday’s open tonight** and cuts the **live** leg. Qwen explains. The kernel sizes.

This is not a chatbot. It is not a Bitget API trading bot. Public prices + a paper book.

## Show it (90 seconds)

```powershell
.\start.ps1
```

Open http://127.0.0.1:8080 · cockpit http://127.0.0.1:8080/cockpit

Claim boundary (on the desk): paper kernel **yes**. Qwen sizes **no**. Live Bitget fill **not claimed**.

```powershell
.\.venv\Scripts\python -m nightshift judge
```

1. Click **Start 90s show** (or **Live book**)
2. Left **SAFE** = frozen index. Right **DEAD** = Monday p90. Kernel **CUT_LIVE BTC**.
3. Next: cosmetic hedge is not cover. Then quiet **HOLD**.
4. **Share report** → http://127.0.0.1:8080/share — a single HTML page you can screenshot, record, or copy (`reports/latest.html`).

Judges cannot open `127.0.0.1`. Screen-share this tab, or host `reports/latest.html` (GitHub Pages, Drive).

## What it does

Weekend Bitget **freezes** rToken margin at Friday’s extended close (Fri 20:00 ET → Mon 9:30 ET). Crypto PnL is live. Stock-perp marks are clamped to the index. A short NVDA future is not a 10% cash-gap hedge.

Nightshift: three clocks → Monday stress (p50/p90/p99) → HOLD / CUT_LIVE / CONVERT / REFUSE_FAKE_HEDGE. LLM cannot raise size.

## Keys

| Key | Needed? |
|---|---|
| Bitget API | **Optional, read-only.** Snapshot your UTA. Still no live orders. |
| Qwen (`BITGET_QWEN_API_KEY` in `.env`) | Optional. Classifies + narrates. |

To load **your** holdings (not the demo $10k NVIDIA book): Bitget → API keys → **UTA management READ only** (no trade, no withdraw). Put key/secret/passphrase in `.env`. Then **Load my Bitget book** or:

```powershell
.\.venv\Scripts\python -m nightshift bitget
```

```powershell
.\.venv\Scripts\python -m nightshift qwen
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\python -m nightshift stress --offline
```

## Evidence

- `logs/audit.jsonl` — event → decision
- `logs/fills.jsonl` — paper fills (**Seed fills** if empty)
- `reports/latest.html` — shareable autopsy
- Stress harness: scenarios, BTC shock grid, weekend klines, checksum, injection

Not investment advice. Paper UTA only.
