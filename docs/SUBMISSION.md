# Nightshift — form paste pack (Bitget S2)

**Do not submit until GitHub is public, the X post exists, and a demo video is uploaded.**  
Those three missing links make a form **invalid** even if the code is good.

Form: https://forms.gle/GyWZCMCPocgJdJon6  
Deadline: **27 September 2026, 23:59 UTC+8** (handbook; not the old Sep 21 date).

Must **quote** this post in your X thread:  
https://x.com/Bitget_AI/status/2100519318824055159?s=20  
Plus `#BitgetHackathon` and `@Bitget_AI`. A bare retweet does not count.

---

## Track

- Track: **Agentic Trading**
- Sub-theme: **Cross-Asset Execution Agent**
- (Optional second entry later: AI Trading Desk / Decision Stress Testing — not this form.)

## Project name

Nightshift

## One-line summary (≤140 characters)

Nightshift prices Monday’s Bitget UTA open tonight: frozen rToken collateral vs live crypto. Qwen narrates; kernel sizes. Paper only.

(Character count: 128)

---

## Project description (paste as one field)

### 1. Thesis

Bitget weekend rToken trading is not Nasdaq. On weekends and US holidays the **rToken index used for UTA margin is frozen** at the last extended-session close (Friday 20:00 ET through Monday 9:30 ET). Crypto futures PnL stays live. Stock-perp marks are clamped to the index (typically ±3%, ±5% on NVDA/AAPL/TSLA/QQQ). A Saturday NVIDIA rumor can therefore leave the UI looking healthy while Monday’s cash open reprices collateral in one print. Stops do not survive that gap.

Nightshift’s hypothesis: an agent that **hedges the ticker from a headline** will fail here (the stock-perp hedge cannot fully print). The useful agent **stresses the whole UTA** (frozen rToken credit + live BTC PnL) and only cuts the **unbanded** live leg, with “do nothing” as a first-class action.

Pipeline: public Bitget clocks → session calendar → news label (rules + optional Qwen) → Monday p50/p90/p99 margin resource vs initial margin → HOLD / CUT_LIVE / CONVERT_COLLATERAL / REFUSE_FAKE_HEDGE. The LLM cannot raise size or send an exchange order.

### 2. Target user and product value

Not “all traders.” Target: Bitget UTA user, roughly **$5k–$50k**, Asia/EU timezone so US cash close is bedtime, holding **1–3 mega-cap rTokens as margin** and a **crypto perp** (often BTC) on the same account. They want to **wake up still in the game**, not a sentiment bot. Value: see Screen vs Monday p90 in 90 seconds and a kernel that can say HOLD.

### 3. Validation data and key metrics

Labeled **observed (local paper / harness)**, not live exchange PnL.

- Offline harness: **18/18** (scenarios, BTC shock 0% to −16%, never-increase-IM, injection, checksum).
- Pytest: **32 passed** (kernel, calendar Fri-night/Mon-preopen freeze, API, receipts, Bitget book mapper).
- Frozen-illusion demo (observed): screen display **SAFE** (~24× display MMR) vs Monday p90 **DEAD**; kernel **CUT_LIVE ~25% BTCUSDT**; replay without agent DEAD / with kernel SAFE.
- Paper fills JSONL fields: timestamp, instrument, direction, price, quantity, cash_delta (Agentic required schema). Soak Sharpe / max DD / win rate computed from committed autopsies (seed or Commit cuts).
- Not claimed: Bitget live fill IDs, Agent Hub `--paper-trading` Demo orders, 60-day Alpha Factory backtest.

### 4. Progress

Built: FastAPI desk, 90s show, live Bitget public marks, optional read-only UTA snapshot, Qwen 3.8 Max classify+narrate, hash-chained evaluate receipts, share HTML, judge cockpit, `nightshift judge` pack.  
Not built for this entry: public hosted URL (127.0.0.1 only until GitHub Pages), live Bitget orders, two-week overnight soak on Demo.

### 5. Deliverables

See Submission Material Links below (GitHub, share HTML, paper logs, cockpit).

### 6. Take on AI trading

Live LLM trading records in 2026 show weak directional edge and volatility-blind sizing. Nightshift treats the model as a **reader**, not the risk engine. That is the product.

---

## Role of the LLM

**Qwen 3.8 Max** (`qwen3.8-max`, Bitget hackathon OpenAI-compatible endpoint).

- Does: classify headlines (nvidia_idio / crypto_beta / earnings / …); write 2–3 sentence judge narration from a **locked** kernel JSON.
- Does not: size, pick leverage, or place Bitget orders.
- Rules win on `crypto_beta` / `none` so prompt injection cannot mint an NVDA gap.
- If Qwen is down, rules-only still runs.

---

## Submission material links (one per line, labeled)

```
Demo (local): http://127.0.0.1:8080  — judges cannot use this; attach a screen-recording of Start 90s show + Live book
Share autopsy HTML: reports/latest.html (also /share when the desk is running)
Judge cockpit: http://127.0.0.1:8080/cockpit  — POST /api/evaluate writes a receipt, exchange_order=false
Code: [PUBLIC GITHUB URL — required]
Paper log: logs/fills.jsonl and logs/audit.jsonl (timestamp, instrument, direction, price, qty, cash_delta)
Receipts: logs/receipts.jsonl (hash chain)
README: repo root
```

Replace the GitHub line after you push. Add YouTube/unlisted video URL. **Do not paste 127.0.0.1 as the only project link.**

---

## X post draft (you must post this yourself)

Quote https://x.com/Bitget_AI/status/2100519318824055159

```
Nightshift — an agent for the hours humans sleep, but not a sentiment bot.

Bitget freezes rToken collateral on the weekend. Crypto still moves. Monday can liquidate a UTA that looked healthy Saturday.

Nightshift prices Monday’s open tonight. Qwen explains. The kernel sizes (and can HOLD).

#BitgetHackathon @Bitget_AI
[GitHub] [video]
```

---

## Go / no-go

| Item | Status |
|---|---|
| Product / tests / stress | **OK to describe** |
| Track + thesis | **OK** |
| Public GitHub + README | **BLOCKER** |
| X post + quote official tweet | **BLOCKER** |
| Demo video (required if no public demo URL) | **BLOCKER** |
| Paper logs in a public repo (no `.env`) | **Do before submit** |
