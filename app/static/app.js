const $ = (id) => document.getElementById(id);
const state = { scenarios: [], selected: "frozen_illusion", last: null, busy: false, showStep: -1 };

const SHOW = [
  { id: "live", copy: "1/3 Live book — left SAFE (frozen NVIDIA), right DEAD (Monday). Kernel cuts Bitcoin." },
  { id: "fake_hedge", copy: "2/3 Cosmetic hedge — a short NVIDIA future is not cover. Mark is capped." },
  { id: "quiet_hold", copy: "3/3 Quiet HOLD — no leverage, no news. Doing nothing is the trade." },
];

const money = (n) =>
  n == null || Number.isNaN(Number(n))
    ? "—"
    : Number(n).toLocaleString(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 0 });

const px = (n, d = 2) => (n == null || Number.isNaN(Number(n)) ? "—" : Number(n).toLocaleString(undefined, { maximumFractionDigits: d }));

function toast(msg) {
  const el = $("toast");
  el.hidden = false;
  el.textContent = msg;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { el.hidden = true; }, 4200);
}

function setBusy(on) {
  state.busy = on;
  document.querySelectorAll(".btn").forEach((b) => { b.disabled = on; });
}

async function j(url, opts) {
  const r = await fetch(url, opts);
  let data = null;
  try { data = await r.json(); } catch { data = null; }
  if (!r.ok) {
    const d = data && data.detail;
    const msg = Array.isArray(d) ? d.map((x) => x.msg || JSON.stringify(x)).join("; ") : (d || r.statusText);
    throw new Error(msg);
  }
  return data;
}

function coverage(s) {
  if (!s || !s.im) return 1.4;
  return s.margin_resource / (s.im * 1.15);
}

function gaugeHtml(s, tone) {
  const c = Math.max(0, Math.min(1.6, coverage(s)));
  const pct = Math.min(100, (c / 1.5) * 100);
  const r = 42;
  const circ = 2 * Math.PI * r;
  const dash = circ * (1 - pct / 100);
  const color = tone === "DEAD" || tone === "CUT_LIVE" ? "#ff5d73" : tone === "CALL" || tone === "TIGHT" ? "#e8b86d" : "#3ee6b6";
  return `<svg viewBox="0 0 118 118" aria-hidden="true">
    <circle cx="59" cy="59" r="${r}" fill="none" stroke="rgba(243,239,230,.08)" stroke-width="8"/>
    <circle cx="59" cy="59" r="${r}" fill="none" stroke="${color}" stroke-width="8"
      stroke-linecap="round" stroke-dasharray="${circ}" stroke-dashoffset="${dash}"
      transform="rotate(-90 59 59)"/>
    <text class="val" x="59" y="56" text-anchor="middle">${s ? (c * 100).toFixed(0) : "—"}%</text>
    <text class="label" x="59" y="74" text-anchor="middle">resource / IM+</text>
  </svg>`;
}

function metricsHtml(s) {
  if (!s) return "";
  const rows = [
    ["Equity", money(s.equity)],
    ["Credit", money(s.collateral_credit)],
    ["Resource", money(s.margin_resource)],
    ["Initial margin", money(s.im)],
    ["Display MMR", money(s.mm)],
    ["Display ratio", s.display_ratio == null ? "—" : `${Number(s.display_ratio).toFixed(1)}×`],
  ];
  return rows.map(([k, v]) => `<div><span>${k}</span><b>${v}</b></div>`).join("");
}

function setBadge(id, label) {
  const el = $(id);
  el.textContent = label || "—";
  el.className = "badge " + (label || "");
}

function setSnap(statusId, metricsId, gaugeId, snap, useDisplay) {
  const label = snap ? (useDisplay ? snap.display_status : snap.status) : "—";
  setBadge(statusId, label);
  $(metricsId).innerHTML = metricsHtml(snap);
  $(gaugeId).innerHTML = gaugeHtml(snap, label);
}

function renderScenarios() {
  $("sceneList").innerHTML = state.scenarios
    .map((s) => `<button type="button" class="scene ${s.id === state.selected ? "active" : ""}" data-id="${s.id}">
      <b>${s.title || s.id}</b><span>${s.kicker || ""}</span>
    </button>`)
    .join("");
  $("sceneList").onclick = (e) => {
    const btn = e.target.closest(".scene");
    if (!btn) return;
    state.selected = btn.dataset.id;
    const row = state.scenarios.find((x) => x.id === state.selected);
    if (row) $("blurb").textContent = row.blurb;
    renderScenarios();
  };
}

function renderTape(payload) {
  if (payload.session) {
    const pill = $("sessionPill");
    pill.classList.toggle("dark", !payload.session.cash_open);
    pill.querySelector("span").textContent = payload.session.label;
  }
  const bits = [];
  for (const c of payload.clocks || []) {
    bits.push(`<div class="tick ${c.cash_frozen ? "frozen" : ""}">
      <div class="k">${c.ticker} rToken</div>
      <div class="v">${px(c.rtoken_last)}</div>
      <div class="s">${c.cash_frozen ? "index frozen" : "cash live"} · ${px(c.cash_last)}</div>
    </div>`);
    bits.push(`<div class="tick">
      <div class="k">${c.ticker} perp</div>
      <div class="v">${px(c.perp_mark)}</div>
      <div class="s">${c.basis_rtoken_vs_perp_bps == null ? "—" : px(c.basis_rtoken_vs_perp_bps, 1) + " bps"}</div>
    </div>`);
  }
  if (payload.btc && payload.btc.mark) {
    bits.push(`<div class="tick">
      <div class="k">BTC mark</div>
      <div class="v">${px(payload.btc.mark, 1)}</div>
      <div class="s">live · not frozen</div>
    </div>`);
  }
  $("tape").innerHTML = bits.join("");
  $("clockStamp").textContent = new Date().toLocaleTimeString();
}

function renderPositions(account) {
  if (!account) {
    $("positions").innerHTML = `<div class="empty">Run a scenario or live book.</div>`;
    $("bookLabel").textContent = "No positions loaded";
    return;
  }
  $("bookLabel").textContent = account.label || "paper";
  const rows = [];
  for (const c of account.collaterals || []) {
    rows.push(`<div class="row">
      <div class="sym">r${c.ticker}</div>
      <div class="muted">collateral</div>
      <div>${money(c.index_value)} · ${(c.ratio * 100).toFixed(0)}%</div>
    </div>`);
  }
  for (const p of account.perps || []) {
    rows.push(`<div class="row">
      <div class="sym">${p.symbol} ${p.side}</div>
      <div class="muted">${p.leverage}x ${p.is_stock ? "stock" : "crypto"}</div>
      <div>${money(p.notional)} · PnL ${money(p.upnl)}</div>
    </div>`);
  }
  $("positions").innerHTML = rows.length ? rows.join("") : `<div class="empty">Empty book.</div>`;
}

function renderPercentiles(d) {
  const bits = ["p50", "p90", "p99"].map((k) => {
    const s = d[k];
    if (!s) return "";
    return `<span class="chip ${s.status}">${k} ${s.status} · ${money(s.margin_resource)}</span>`;
  });
  $("pctRow").innerHTML = bits.join("");
}

async function loadFills() {
  try {
    const data = await j("/api/blotter");
    const fills = data.fills || [];
    const soak = data.soak || {};
    if (soak.n) {
      $("stressSummary").textContent =
        `Soak n=${soak.n} · Sharpe ${soak.sharpe ?? "—"} · max DD ${soak.max_drawdown} · win ${((soak.win_rate || 0) * 100).toFixed(0)}%`;
    }
    if (!fills.length) {
      $("fillsLog").innerHTML = `<div class="empty">No fills. Click Seed fills or check Commit cuts.</div>`;
      return;
    }
    $("fillsLog").innerHTML = fills
      .slice(-12)
      .reverse()
      .map((f) => `<div>${f.ts || ""} · ${f.kind} ${f.direction} ${f.instrument} @ ${f.price} · cash ${money(f.cash_delta)}</div>`)
      .join("");
  } catch {
    $("fillsLog").innerHTML = `<div class="empty">Blotter unavailable.</div>`;
  }
}

function renderDecision(data) {
  state.last = data;
  const d = data.decision;
  if (d.session) {
    $("sessionPill").classList.toggle("dark", !!d.session.cash_closed);
    $("sessionPill").querySelector("span").textContent = d.session.label;
  }
  $("blurb").textContent = data.blurb || "";
  setSnap("screenStatus", "screenMetrics", "screenGauge", d.screen, true);
  setSnap("mondayStatus", "mondayMetrics", "mondayGauge", d.p90, false);
  setBadge("action", d.action);
  $("reason").textContent = data.narration || d.reason || "";
  $("legs").innerHTML = (d.legs || [])
    .map((leg) => `<div class="leg"><code>${leg.kind}</code> ${leg.symbol} ${(leg.fraction * 100).toFixed(0)}% — ${leg.note}</div>`)
    .join("");
  $("fake").textContent = (d.fake_hedges || []).map((f) => f.note).join(" ");
  renderPercentiles(d);
  renderPositions(data.account);
  if (d.p90) {
    $("replayRow").hidden = false;
    setBadge("woStatus", d.p90.status);
    $("woMetrics").innerHTML = metricsHtml(d.p90);
    const withK = d.after || d.p90;
    setBadge("wStatus", withK.status);
    $("wMetrics").innerHTML = metricsHtml(withK);
  }
}

async function loadScenarios() {
  const data = await j("/api/scenarios");
  state.scenarios = data.scenarios;
  renderScenarios();
}

async function loadHealth() {
  try {
    const h = await j("/api/health");
    $("sessionPill").classList.toggle("dark", !h.session.cash_open);
    $("sessionPill").querySelector("span").textContent = h.session.label;
    const qb = $("qwenBadge");
    if (h.qwen && h.qwen.configured) {
      qb.textContent = `Qwen ${h.qwen.model} ready`;
      qb.style.color = "var(--teal)";
    } else {
      qb.textContent = "Qwen off — add BITGET_QWEN_API_KEY";
    }
    const bc = $("bitgetClaim");
    if (bc && h.bitget) {
      bc.textContent = h.bitget.configured ? "key in .env" : "optional";
      bc.className = h.bitget.configured ? "ok" : "no";
    }
  } catch {
    $("sessionPill").querySelector("span").textContent = "SESSION UNKNOWN";
  }
}

async function loadClocks() {
  try {
    renderTape(await j("/api/clocks"));
  } catch (e) {
    $("tape").innerHTML = `<div class="tick"><div class="k">tape</div><div class="v">${e.message}</div></div>`;
  }
}

async function loadAudit() {
  const data = await j("/api/audit");
  if (!data.rows.length) {
    $("audit").innerHTML = `<div class="empty">No runs yet.</div>`;
    return;
  }
  $("audit").innerHTML = data.rows
    .slice(0, 14)
    .map((r) => {
      const d = r.decision || {};
      const news = d.news?.label || "—";
      const sess = d.session?.kind || "—";
      const why = (d.reason || "").slice(0, 160);
      const legs = (d.legs || []).map((l) => `${l.kind} ${l.symbol}`).join(", ") || "none";
      const fills = (r.fills || []).length;
      return `<div><b>${r.ts}</b> · ${sess} · ${news} · ${d.action || ""} · ${r.applied ? "COMMIT" : "DRY"}<br/>${why}<br/>legs ${legs} · fills ${fills} · ${r.run_id}</div>`;
    })
    .join("");
}

async function run() {
  setBusy(true);
  try {
    const data = await j("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        scenario: state.selected,
        headline: $("headline").value,
        apply: $("commitPaper").checked,
        use_llm: $("useQwen").checked,
      }),
    });
    renderDecision(data);
    await loadAudit();
    await loadFills();
  } catch (e) { toast(e.message); } finally { setBusy(false); }
}

async function live() {
  setBusy(true);
  try {
    const data = await j("/api/live", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        headline: $("headline").value,
        apply: $("commitPaper").checked,
        force_weekend: true,
        use_llm: $("useQwen").checked,
      }),
    });
    if (data.clocks) renderTape(data.clocks);
    renderDecision(data);
    await loadAudit();
    await loadFills();
  } catch (e) { toast(e.message); } finally { setBusy(false); }
}

async function replay() {
  const cached = state.last && state.last.decision;
  if (cached && cached.p90) {
    $("replayRow").hidden = false;
    setBadge("woStatus", cached.p90.status);
    $("woMetrics").innerHTML = metricsHtml(cached.p90);
    const withK = cached.after || cached.p90;
    setBadge("wStatus", withK.status);
    $("wMetrics").innerHTML = metricsHtml(withK);
    return;
  }
  setBusy(true);
  try {
    const data = await j("/api/replay", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        scenario: state.selected,
        headline: $("headline").value,
        which: "p90",
      }),
    });
    $("replayRow").hidden = false;
    setBadge("woStatus", data.without_agent.status);
    $("woMetrics").innerHTML = metricsHtml(data.without_agent);
    setBadge("wStatus", data.with_agent.status);
    $("wMetrics").innerHTML = metricsHtml(data.with_agent);
  } catch (e) { toast(e.message); } finally { setBusy(false); }
}

async function stress() {
  setBusy(true);
  $("stressSummary").textContent = "Running harness…";
  try {
    const data = await j("/api/stress", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ live: true }),
    });
    $("stressSummary").textContent = `${data.passed}/${data.total} passed · ${data.failed} failed`;
    $("stressLog").innerHTML = data.cases
      .map((c) => `<div class="${c.ok ? "ok" : "bad"}">${c.ok ? "PASS" : "FAIL"} ${c.name} — ${c.detail}</div>`)
      .join("");
  } catch (e) { toast(e.message); } finally { setBusy(false); }
}

$("run").onclick = run;
async function myBitget() {
  setBusy(true);
  try {
    const data = await j("/api/bitget/autopsy", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        headline: $("headline").value,
        force_weekend: true,
        use_llm: $("useQwen").checked,
      }),
    });
    if (data.clocks) renderTape(data.clocks);
    renderDecision(data);
    toast("Loaded your Bitget snapshot. Kernel is still paper — no order sent.");
    await loadAudit();
  } catch (e) {
    toast(e.message);
  } finally { setBusy(false); }
}

$("liveBtn").onclick = live;
$("myBitgetBtn").onclick = myBitget;
$("replay").onclick = replay;
async function soak() {
  try {
    const s = await j("/api/soak");
    $("stressSummary").textContent =
      s.n === 0
        ? "Soak: no committed fills yet. Check Commit cuts, then run."
        : `Soak n=${s.n} · Sharpe ${s.sharpe ?? "—"} · max DD ${s.max_drawdown} · win ${((s.win_rate || 0) * 100).toFixed(0)}% · Σ ${s.sum_pnl}`;
  } catch (e) { toast(e.message); }
}

async function seed() {
  setBusy(true);
  try {
    const data = await j("/api/demo/seed", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    toast("Seeded one committed frozen-index fill.");
    await loadFills();
    await loadAudit();
    if (data.soak) soak();
  } catch (e) { toast(e.message); } finally { setBusy(false); }
}

async function runShowStep() {
  const step = SHOW[state.showStep];
  if (!step) return;
  $("showCopy").textContent = step.copy;
  $("showNext").hidden = false;
  $("showStart").hidden = true;
  if (step.id === "live") {
    $("headline").value = "NVIDIA China chip license in doubt Saturday";
    await live();
    return;
  }
  state.selected = step.id;
  renderScenarios();
  await run();
}

$("showStart").onclick = async () => {
  state.showStep = 0;
  await runShowStep();
};
$("showNext").onclick = async () => {
  state.showStep += 1;
  if (state.showStep >= SHOW.length) {
    $("showCopy").textContent = "Done. Open Share report for a page you can send. Screen-share this tab for live.";
    $("showNext").hidden = true;
    $("showStart").hidden = false;
    state.showStep = -1;
    return;
  }
  await runShowStep();
};
$("showSkip").onclick = () => { $("showBar").hidden = true; };

$("stressBtn").onclick = stress;
$("soakBtn").onclick = soak;
$("seedBtn").onclick = seed;
$("clocksBtn").onclick = () => loadClocks().catch((e) => toast(e.message));

document.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) run();
});

loadScenarios()
  .then(loadHealth)
  .then(loadClocks)
  .then(loadAudit)
  .then(loadFills)
  .then(async () => {
    setInterval(() => loadClocks().catch(() => {}), 15000);
    const qwenOn = $("useQwen").checked;
    $("useQwen").checked = false;
    toast("Loading live book on today's Bitget marks…");
    await live();
    $("useQwen").checked = qwenOn;
  })
  .catch((e) => toast(e.message));
