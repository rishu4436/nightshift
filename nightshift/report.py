"""Self-contained HTML autopsy a judge can open without the server."""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "reports"


def _esc(v: object) -> str:
    return html.escape("" if v is None else str(v))


def _money(n: object) -> str:
    try:
        return f"${float(n):,.0f}"
    except (TypeError, ValueError):
        return "—"


def render(payload: dict) -> str:
    d = payload.get("decision") or {}
    screen = d.get("screen") or {}
    p90 = d.get("p90") or {}
    after = d.get("after") or p90
    news = d.get("news") or {}
    sess = d.get("session") or {}
    legs = d.get("legs") or []
    narration = payload.get("narration") or d.get("explanation") or d.get("reason") or ""
    blurb = payload.get("blurb") or ""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    legs_html = "".join(
        f"<li><code>{_esc(x.get('kind'))}</code> {_esc(x.get('symbol'))} "
        f"{float(x.get('fraction') or 0)*100:.0f}% — {_esc(x.get('note'))}</li>"
        for x in legs
    ) or "<li>HOLD — no legs</li>"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>NIGHTSHIFT autopsy — {_esc(d.get('action'))}</title>
  <style>
    body {{ margin:0; background:#08090c; color:#f3efe6; font:16px/1.45 Instrument Sans, system-ui, sans-serif; }}
    main {{ max-width:880px; margin:0 auto; padding:40px 20px 80px; }}
    h1 {{ font-family: Syne, sans-serif; letter-spacing:-.03em; }}
    h1 span {{ color:#3ee6b6; }}
    .row {{ display:grid; grid-template-columns:1fr 1fr; gap:14px; }}
    .card {{ border:1px solid rgba(243,239,230,.12); border-radius:16px; padding:18px; background:rgba(16,18,24,.8); }}
    .SAFE,.HOLD {{ color:#3ee6b6; }}
    .DEAD,.CUT_LIVE,.CONVERT_COLLATERAL {{ color:#ff5d73; }}
    .CALL,.TIGHT,.REFUSE_FAKE_HEDGE {{ color:#e8b86d; }}
    .mute {{ color:#9b968b; font-size:13px; }}
    code {{ color:#3ee6b6; }}
    @media (max-width:700px) {{ .row {{ grid-template-columns:1fr; }} }}
  </style>
</head>
<body>
<main>
  <p class="mute">Nightshift · Bitget AI Hackathon S2 · Cross-Asset Execution · {ts}</p>
  <h1>NIGHT<span>SHIFT</span></h1>
  <p>While you sleep, Bitget freezes rToken collateral and keeps trading your crypto.
     This page is one autopsy: screen vs Monday p90 vs kernel. Qwen explains. The kernel sizes.</p>
  <p>{_esc(blurb)}</p>
  <div class="row">
    <div class="card">
      <p class="mute">Screen (frozen index)</p>
      <h2 class="{_esc(screen.get('display_status'))}">{_esc(screen.get('display_status'))}</h2>
      <p>Equity {_money(screen.get('equity'))} · resource {_money(screen.get('margin_resource'))} · IM {_money(screen.get('im'))}</p>
    </div>
    <div class="card">
      <p class="mute">Monday p90</p>
      <h2 class="{_esc(p90.get('status'))}">{_esc(p90.get('status'))}</h2>
      <p>Equity {_money(p90.get('equity'))} · resource {_money(p90.get('margin_resource'))} · IM {_money(p90.get('im'))}</p>
    </div>
  </div>
  <div class="card" style="margin-top:14px">
    <p class="mute">Kernel · session {_esc(sess.get('kind'))} · news {_esc(news.get('label'))}</p>
    <h2 class="{_esc(d.get('action'))}">{_esc(d.get('action'))}</h2>
    <p>{_esc(narration)}</p>
    <ul>{legs_html}</ul>
    <p class="mute">Without kernel Monday is {_esc(p90.get('status'))}. With kernel: {_esc(after.get('status'))}.</p>
  </div>
  <p class="mute">Not investment advice. Paper UTA. No Bitget private API required for this snapshot.</p>
</main>
</body>
</html>
"""


def save(payload: dict) -> Path:
    REPORTS.mkdir(parents=True, exist_ok=True)
    path = REPORTS / "latest.html"
    path.write_text(render(payload), encoding="utf-8")
    (REPORTS / "latest.json").write_text(json.dumps(payload, indent=2)[:200000], encoding="utf-8")
    return path
