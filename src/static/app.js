const $ = (id) => document.getElementById(id);

// --- number formatting (API returns raw floats; format at the render edge) ---
const _n = (v) => (v == null || v === "" || isNaN(Number(v))) ? null : Number(v);
const num = (v, d = 2) => { const n = _n(v); return n == null ? "-" : n.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d }); };
const price = (v) => { const n = _n(v); if (n == null) return "-"; const d = Math.abs(n) < 1 ? 4 : 2; return "$" + n.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d }); };
const money = (v, d = 2) => { const n = _n(v); return n == null ? "-" : "$" + n.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d }); };
const pct = (v, d = 2) => { const n = _n(v); return n == null ? "-" : (n >= 0 ? "+" : "") + n.toFixed(d) + "%"; };
const signed = (v, d = 2) => { const n = _n(v); return n == null ? "-" : (n >= 0 ? "+" : "") + n.toFixed(d); };

async function fetchJSON(url, opts) {
  const res = await fetch(url, opts);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || res.statusText);
  }
  return res.json();
}

function colorForScore(score) {
  if (score > 1) return "rgba(46,204,113,0.35)";
  if (score > 0) return "rgba(46,204,113,0.15)";
  if (score > -1) return "rgba(231,76,60,0.15)";
  return "rgba(231,76,60,0.35)";
}

async function loadRegime() {
  const el = $("regime-content");
  try {
    const r = await fetchJSON("/api/regime");
    el.innerHTML = `
      <div class="regime-badge regime-${r.regime}">${r.regime}</div>
      <p>${r.symbol} ${price(r.price)} &middot; RSI ${num(r.rsi, 1)} (${r.condition})</p>
      <p class="muted">1d ${pct(r.trend_1d, 1)} &middot; 5d ${pct(r.trend_5d, 1)} &middot; 10d ${pct(r.trend_10d, 1)} &middot; 30d ${pct(r.trend_30d, 1)}</p>
    `;
  } catch (e) {
    el.innerHTML = `<p class="muted">${e.message}</p>`;
  }
}

async function loadAccounts() {
  const el = $("accounts-content");
  try {
    const accounts = await fetchJSON("/api/accounts");
    el.innerHTML = accounts.map(a => {
      const balance = a.hidden
        ? '<span class="muted">balance hidden</span>'
        : `${money(a.current_balance)} <span class="muted">(started ${money(a.starting_balance, 0)})</span>`;
      return `<p><span class="tag tag-${a.account_type}">${a.account_type}</span> ${balance}</p>`;
    }).join("") || '<p class="muted">No accounts seeded yet</p>';
  } catch (e) {
    el.innerHTML = `<p class="muted">${e.message}</p>`;
  }
}

async function loadPerformance() {
  const el = $("performance-content");
  try {
    const perf = await fetchJSON("/api/performance");
    if (!perf.length) {
      el.innerHTML = '<p class="muted">No performance snapshots yet</p>';
      return;
    }
    el.innerHTML = perf.slice(0, 5).map(p => {
      // Show % return but not the dollar total for hidden accounts.
      const value = p.hidden ? "" : `${money(p.total_value)} `;
      return `<p><span class="tag tag-${p.account_type}">${p.account_type}</span>
      ${p.date}: ${value}(${pct(p.total_pnl_pct, 1)})</p>`;
    }).join("");
  } catch (e) {
    el.innerHTML = `<p class="muted">${e.message}</p>`;
  }
}

async function loadSectors() {
  const el = $("sector-heatmap");
  try {
    const [sectors, turning] = await Promise.all([
      fetchJSON("/api/sectors"),
      fetchJSON("/api/turning-sectors").catch(() => []),
    ]);
    if (!sectors.length) {
      el.innerHTML = '<p class="muted">No sector data yet — the engine populates this on its next scan.</p>';
      return;
    }
    const turnSet = new Set(turning);
    el.innerHTML = sectors.map(s => {
      const isTurning = turnSet.has(s.sector_name);
      return `
      <div class="sector-tile clickable ${isTurning ? "turning" : ""}" data-sector="${s.sector_name}"
           style="background:${colorForScore(s.composite_score)}">
        <span class="name">#${s.rank} ${s.sector_name} ${isTurning ? '<span class="turn-mark" title="laggard turning up">↗</span>' : ""}</span>
        <span class="muted">${s.etf_symbol}</span><br>
        ${signed(s.composite_score)}
      </div>`;
    }).join("");
    el.querySelectorAll(".sector-tile").forEach(tile =>
      tile.addEventListener("click", () => loadSectorSetups(tile.dataset.sector)));
  } catch (e) {
    el.innerHTML = `<p class="muted">${e.message}</p>`;
  }
}

function setupTable(setups) {
  return `<table>
    <thead><tr>
      <th>Symbol</th><th>Confidence</th><th>Entry</th><th>Stop</th><th>Target</th>
      <th>R:R</th><th>Return</th><th>Structure</th><th>RVOL</th>
    </tr></thead>
    <tbody>${setups.map(s => `
      <tr>
        <td><strong>${s.symbol}</strong>${s.direction === "short" ? ' <span class="short-tag">SHORT ▼</span>' : ""}</td>
        <td><span class="conf conf-${s.confidence}">${s.confidence}</span>
            <span class="muted">${s.num_edges}e</span></td>
        <td>${price(s.entry_price)}</td>
        <td>${price(s.stop_loss)}</td>
        <td>${price(s.target_price)}</td>
        <td>${num(s.risk_reward, 1)}:1</td>
        <td>${pct(s.expected_return_pct, 1)}</td>
        <td class="muted">D:${s.daily_bias} / W:${s.weekly_bias}</td>
        <td>${num(s.rvol, 1)}</td>
      </tr>
      <tr><td colspan="9"><div class="edges muted">✓ ${(s.edges_fired || "").split(", ").join(" · ")}</div></td></tr>
    `).join("")}</tbody>
  </table>`;
}

// sector-view filter state
const sectorFilters = { sector: null, horizon: "swing", direction: "long", maxPrice: 50 };

function filterBar() {
  const p = sectorFilters;
  const btn = (label, key, val) =>
    `<button class="chip ${p[key] === val ? "on" : ""}" data-key="${key}" data-val="${val}">${label}</button>`;
  const shortDir = p.direction === "short";
  return `<div class="filterbar">
    <span class="filter-label">Direction:</span>
    ${btn("▲ Long (upside)", "direction", "long")}
    ${btn("▼ Short (downside)", "direction", "short")}
    <span class="filter-label" style="margin-left:14px">Horizon:</span>
    ${shortDir ? '<span class="muted" style="font-size:11px">swing (long-only)</span>' :
      btn("Swing (days–wks)", "horizon", "swing") + btn("Short-term (1-3d)", "horizon", "short")}
    <span class="filter-label" style="margin-left:14px">Price:</span>
    ${btn("Under $50", "maxPrice", 50)}
    ${btn("Under $5", "maxPrice", 5)}
    ${btn("All", "maxPrice", 0)}
  </div>`;
}

async function loadSectorSetups(sector) {
  if (sector) sectorFilters.sector = sector;
  const s = sectorFilters.sector;
  const el = $("sector-setups");
  const priceQ = sectorFilters.maxPrice ? `&max_price=${sectorFilters.maxPrice}` : "";
  const url = `/api/sector/${encodeURIComponent(s)}/setups?horizon=${sectorFilters.horizon}` +
    `&direction=${sectorFilters.direction}${priceQ}`;
  const dirLabel = sectorFilters.direction === "short" ? "downside/short" : "";
  const kind = (sectorFilters.direction === "short" ? "downside " : "") +
    (sectorFilters.horizon === "short" && sectorFilters.direction !== "short" ? "1-3 day breakout" : "swing");
  el.innerHTML = `${filterBar()}<p class="muted">Analyzing ${s} — ${kind} analysis on each name, ~10-20s...</p>`;
  el.scrollIntoView({ behavior: "smooth", block: "nearest" });
  try {
    const r = await fetchJSON(url);
    const scoreTxt = r.composite_score == null ? "n/a" : signed(r.composite_score);
    const priceTxt = sectorFilters.maxPrice ? `under $${sectorFilters.maxPrice}` : "any price";
    const header = `<h3>${s} — ${kind} setups (${priceTxt})
      <span class="muted">(sector score ${scoreTxt}; bar = ${r.selectivity}+
      ${r.selectivity === "HIGH" ? "— neutral, extra selective" : "— hot"}; scanned ${r.candidates_scanned})</span>
      <button class="reject" style="float:right;padding:2px 8px" onclick="document.getElementById('sector-setups').innerHTML=''">Close</button></h3>`;
    el.innerHTML = filterBar() + header + (r.setups.length
      ? setupTable(r.setups)
      : `<p class="muted">No ${priceTxt} names in ${s} cleared the ${r.selectivity}+ bar for this horizon right now.</p>`);
    el.querySelectorAll(".chip").forEach(chip => chip.addEventListener("click", () => {
      const key = chip.dataset.key;
      sectorFilters[key] = key === "maxPrice" ? Number(chip.dataset.val) : chip.dataset.val;
      loadSectorSetups();
    }));
  } catch (e) {
    el.innerHTML = filterBar() + `<p class="muted">${e.message}</p>`;
    el.querySelectorAll(".chip").forEach(chip => chip.addEventListener("click", () => {
      const key = chip.dataset.key;
      sectorFilters[key] = key === "maxPrice" ? Number(chip.dataset.val) : chip.dataset.val;
      loadSectorSetups();
    }));
  }
}

async function actOnProposal(id, action) {
  try {
    await fetchJSON(`/api/proposals/${id}/${action}`, { method: "POST" });
    await loadProposals();
    await loadTrades();
    await loadAccounts();
  } catch (e) {
    alert(`Failed to ${action} proposal ${id}: ${e.message}`);
  }
}

let proposalView = "top";
let proposalCache = [];

const TIMEFRAME_ORDER = ["3-10 days", "1-3 weeks", "2-6 weeks"];
const TIER_ORDER = { HIGH: 3, MEDIUM: 2, LOW: 1 };

function proposalRow(p) {
  return `
    <tr>
      <td><span class="tag tag-${p.account_type}">${p.account_type}</span>
          ${p.strategy === "downside" ? '<br><span class="short-tag">SHORT ▼</span>' : ""}
          ${p.is_microfloat ? '<br><span class="micro-tag">µFLOAT</span>' : ""}</td>
      <td><strong>${p.symbol}</strong><br><span class="muted">${p.sector_name || ""}</span></td>
      <td><span class="conf conf-${p.confidence}">${p.confidence || "-"}</span>
          <br><span class="muted">${p.num_edges || 0} edges</span></td>
      <td>${price(p.entry_price)}</td>
      <td>${price(p.stop_loss)}</td>
      <td>${price(p.target_price)}</td>
      <td>${num(p.risk_reward, 1)}:1</td>
      <td>${num(p.quality_score, 1)}/10</td>
      <td>${money(p.position_size_usd, 0)} (${p.shares} sh)</td>
      <td>${pct(p.expected_return_pct, 1)}</td>
      <td>${p.expected_timeframe}</td>
      <td>
        <button class="approve" onclick="actOnProposal(${p.id}, 'approve')">Approve</button>
        <button class="reject" onclick="actOnProposal(${p.id}, 'reject')">Reject</button>
      </td>
    </tr>
    <tr><td colspan="12">
      <div class="edges muted">✓ ${(p.edges_fired || "").split(", ").join(" · ")}</div>
      <div class="muted">${p.reasoning}</div>
    </td></tr>`;
}

function proposalTable(rows) {
  return `<table>
    <thead><tr>
      <th>Account</th><th>Symbol</th><th>Confidence</th><th>Entry</th><th>Stop</th><th>Target</th>
      <th>R:R</th><th>Quality</th><th>Size</th><th>Exp. Return</th><th>Timeframe</th><th></th>
    </tr></thead>
    <tbody>${rows.map(proposalRow).join("")}</tbody>
  </table>`;
}

function rankProposals(list) {
  return [...list].sort((a, b) =>
    (TIER_ORDER[b.confidence] || 0) - (TIER_ORDER[a.confidence] || 0) ||
    (b.num_edges || 0) - (a.num_edges || 0) ||
    (b.quality_score || 0) - (a.quality_score || 0));
}

function renderProposals() {
  const el = $("proposals-content");
  const proposals = proposalCache;
  if (!proposals.length) {
    el.innerHTML = '<p class="muted">No pending proposals — the engine posts new ideas automatically each scan.</p>';
    return;
  }

  if (proposalView === "top") {
    // top 5 per account
    const byAccount = {};
    for (const p of proposals) (byAccount[p.account_type] ||= []).push(p);
    let html = "";
    for (const [acct, list] of Object.entries(byAccount)) {
      html += `<h3><span class="tag tag-${acct}">${acct}</span> top picks</h3>`;
      html += proposalTable(rankProposals(list).slice(0, 5));
    }
    el.innerHTML = html;
  } else if (proposalView === "shortterm") {
    // momentum ideas for a 5-10% pop in 1-2 days, across sectors
    const st = rankProposals(proposals.filter(p => p.strategy === "short_term"));
    el.innerHTML = `<h3>⚡ Short-term momentum — 5-10% in 1-2 days
      <span class="muted">(${st.length} ideas across sectors)</span></h3>` +
      (st.length ? proposalTable(st)
        : '<p class="muted">No short-term momentum ideas cleared the filters this scan — no clean setups right now.</p>');
  } else if (proposalView === "coiling") {
    // names coiling before a potential breakout (squeeze + accumulation)
    const co = rankProposals(proposals.filter(p => p.strategy === "coiling"));
    el.innerHTML = `<h3>🌀 Coiling — pre-breakout watch
      <span class="muted">(${co.length} names squeezing on quiet accumulation — buy on breakout above entry)</span></h3>` +
      (co.length ? proposalTable(co)
        : '<p class="muted">Nothing coiling right now — no squeeze + accumulation setups this scan.</p>');
  } else if (proposalView === "downside") {
    // bearish/short ideas from negative sectors (target is BELOW entry)
    const ds = rankProposals(proposals.filter(p => p.strategy === "downside"));
    el.innerHTML = `<h3>🔻 Downside / short ideas
      <span class="muted">(${ds.length} shorts from negative sectors — profit if price falls to target)</span></h3>` +
      (ds.length ? proposalTable(ds)
        : '<p class="muted">No downside setups cleared the bar — either no sectors are negative enough, or their names aren\'t breaking down yet.</p>');
  } else if (proposalView === "sector") {
    const bySector = {};
    for (const p of proposals) (bySector[p.sector_name] ||= []).push(p);
    const sectors = Object.keys(bySector).sort();
    el.innerHTML = sectors.map(s =>
      `<h3>${s} <span class="muted">(${bySector[s].length})</span></h3>` +
      proposalTable(rankProposals(bySector[s]))).join("");
  } else if (proposalView === "sectorSM") {
    // For each hot sector: best short-term idea + best medium-term idea.
    const SHORT = new Set(["3-10 days", "1-3 weeks"]);
    const bySector = {};
    for (const p of proposals) (bySector[p.sector_name] ||= []).push(p);
    const sectors = Object.keys(bySector).sort();
    el.innerHTML = sectors.map(s => {
      const ranked = rankProposals(bySector[s]);
      const short = ranked.filter(p => SHORT.has(p.expected_timeframe))[0];
      const medium = ranked.filter(p => p.expected_timeframe === "2-6 weeks")[0];
      const cell = (p, label) => p
        ? `<div class="sm-cell"><div class="sm-label">${label}</div>${proposalTable([p])}</div>`
        : `<div class="sm-cell"><div class="sm-label">${label}</div><p class="muted">no qualifying setup</p></div>`;
      return `<h3>${s}</h3><div class="sm-grid">${cell(short, "Short-term (days–weeks)")}${cell(medium, "Medium-term (2–6 wks)")}</div>`;
    }).join("");
  } else { // timeframe
    const byTf = {};
    for (const p of proposals) (byTf[p.expected_timeframe] ||= []).push(p);
    const order = TIMEFRAME_ORDER.filter(t => byTf[t]).concat(
      Object.keys(byTf).filter(t => !TIMEFRAME_ORDER.includes(t)));
    el.innerHTML = order.map(t =>
      `<h3>${t} <span class="muted">(${byTf[t].length})</span></h3>` +
      proposalTable(rankProposals(byTf[t]))).join("");
  }
}

async function loadProposals() {
  try {
    proposalCache = await fetchJSON("/api/proposals?status=pending");
    renderProposals();
  } catch (e) {
    $("proposals-content").innerHTML = `<p class="muted">${e.message}</p>`;
  }
}

async function loadTrades() {
  const el = $("trades-content");
  try {
    const [positions, trades] = await Promise.all([
      fetchJSON("/api/positions"),
      fetchJSON("/api/trades"),
    ]);
    let html = "<h3>Positions</h3>";
    html += positions.length ? `
      <table><thead><tr><th>Account</th><th>Symbol</th><th>Qty</th><th>Avg</th><th>Current</th><th>Unrl. P/L</th></tr></thead>
      <tbody>${positions.map(p => `
        <tr>
          <td><span class="tag tag-${p.account_type}">${p.account_type}</span></td>
          <td>${p.symbol}</td><td>${p.quantity}</td><td>${price(p.avg_price)}</td>
          <td>${price(p.current_price)}</td>
          <td style="color:${p.unrealized_pnl >= 0 ? 'var(--green)' : 'var(--red)'}">
            ${money(p.unrealized_pnl)} (${pct(p.unrealized_pnl_pct, 1)})
          </td>
        </tr>`).join("")}</tbody></table>
    ` : '<p class="muted">No open positions</p>';

    html += "<h3>Recent Trades</h3>";
    html += trades.length ? `
      <table><thead><tr><th>Account</th><th>Symbol</th><th>Side</th><th>Qty</th><th>Entry</th><th>Status</th></tr></thead>
      <tbody>${trades.slice(0, 20).map(t => `
        <tr>
          <td><span class="tag tag-${t.account_type}">${t.account_type}</span></td>
          <td>${t.symbol}</td><td>${t.side}</td><td>${t.quantity}</td>
          <td>${price(t.entry_price)}</td><td>${t.status}</td>
        </tr>`).join("")}</tbody></table>
    ` : '<p class="muted">No trades yet</p>';

    el.innerHTML = html;
  } catch (e) {
    el.innerHTML = `<p class="muted">${e.message}</p>`;
  }
}

function daysSince(iso) {
  if (!iso) return 0;
  return Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 86400000));
}

// bar-age stamp: never let stale data look live
function ageLabel(sec) {
  if (sec == null) return '<span class="age age-none">no data</span>';
  let txt, cls;
  if (sec < 90) { txt = Math.round(sec) + "s"; cls = "age-live"; }
  else if (sec < 3600) { txt = Math.round(sec / 60) + "m"; cls = "age-warn"; }
  else if (sec < 86400) { txt = (sec / 3600).toFixed(1) + "h"; cls = "age-stale"; }
  else { txt = (sec / 86400).toFixed(1) + "d"; cls = "age-stale"; }
  return `<span class="age ${cls}" title="bar age">${txt}</span>`;
}

// Live paper-trade book: marks every open sim trade to Alpaca's real-time feed.
// Sortable by any column (click header); the row order is CAPTURED on click and
// held stable across the 5s auto-refresh, so rows never reshuffle under you --
// only the values update in place. New positions append at the bottom.
let lastLiveData = { trades: [] };
let liveSort = { col: "live_pnl_pct", dir: -1 };
let liveOrder = null;  // symbols in display order (null until first render)

const LIVE_COLS = [
  { k: "symbol", label: "Symbol", txt: true },
  { k: "entry_price", label: "Entry" },
  { k: "live_price", label: "Current" },
  { k: "position_value", label: "Pos. value" },
  { k: "live_pnl_usd", label: "P&L $" },
  { k: "live_pnl_pct", label: "P&L %" },
  { k: "rs_vs_spy", label: "RS vs SPY" },
  { k: "dist_to_stop_pct", label: "→ Stop" },
  { k: "dist_to_target_pct", label: "→ Target" },
  { k: "days_held", label: "Days" },
];

function sortSymbols(trades, sort) {
  return [...trades].sort((a, b) => {
    const va = a[sort.col], vb = b[sort.col];
    const na = va == null, nb = vb == null;
    if (na && nb) return 0; if (na) return 1; if (nb) return -1;  // nulls always last
    if (typeof va === "string") return va.localeCompare(vb) * sort.dir;
    return (va - vb) * sort.dir;
  }).map(t => t.symbol);
}

function sortLive(col) {
  if (liveSort.col === col) liveSort.dir = -liveSort.dir;
  else liveSort = { col, dir: col === "symbol" ? 1 : -1 };
  liveOrder = sortSymbols(lastLiveData.trades || [], liveSort);  // re-capture order on click
  renderLiveBook(lastLiveData);
}

function liveCell(t, k) {
  const v = t[k];
  if (v == null) return '<span class="muted">—</span>';
  if (k === "symbol") return `<strong>${v}</strong>${t.direction === "short" ? ' <span class="short-tag">▼</span>' : ""}`;
  if (k === "entry_price" || k === "live_price") return price(v) + (k === "live_price" ? " " + ageLabel(t.age_seconds) : "");
  if (k === "position_value") return money(v, 0);
  if (k === "live_pnl_usd") return `<span class="${v >= 0 ? "pos" : "neg"}">${money(v)}</span>`;
  if (k === "days_held") return v;
  // percentage columns, colored by sign
  const cls = (k === "dist_to_stop_pct" || k === "dist_to_target_pct") ? "" : (v >= 0 ? "pos" : "neg");
  return `<span class="${cls}">${pct(v, k === "live_pnl_pct" ? 2 : 1)}</span>`;
}

function renderLiveBook(d) {
  const el = $("paper-open-content"); if (!el) return;
  const trades = d.trades || [];
  if (!trades.length) {
    el.innerHTML = '<p class="muted">No open trades yet — the engine opens them automatically as setups qualify.</p>';
    liveOrder = null; return;
  }
  const bySym = {}; trades.forEach(t => bySym[t.symbol] = t);
  // capture initial order once; thereafter keep it stable (drop gone, append new)
  if (liveOrder === null) liveOrder = sortSymbols(trades, liveSort);
  const known = new Set(liveOrder);
  liveOrder = liveOrder.filter(s => bySym[s]).concat(trades.map(t => t.symbol).filter(s => !known.has(s)));
  const ordered = liveOrder.map(s => bySym[s]).filter(Boolean);

  const maxAge = Math.max(...trades.map(t => t.age_seconds ?? 0));
  const feed = d.alpaca_enabled
    ? `<span class="age ${maxAge < 90 ? "age-live" : "age-stale"}">${maxAge < 90 ? "🟢 LIVE" : "⚠ stale"}</span> Alpaca IEX`
    : '<span class="muted">Alpaca off — showing plan only</span>';
  const spy = d.spy || {};
  const arrow = (k) => liveSort.col === k ? (liveSort.dir < 0 ? " ▼" : " ▲") : "";
  const head = LIVE_COLS.map(c =>
    `<th class="sortable ${liveSort.col === c.k ? "sorted" : ""}" onclick="sortLive('${c.k}')">${c.label}${arrow(c.k)}</th>`).join("");

  el.innerHTML =
    `<p class="muted">${d.open_count} open · ${d.priced_count} priced live · ${feed}
      · SPY ${price(spy.price)} ${spy.session_pct != null ? "(" + pct(spy.session_pct, 1) + " session)" : ""}
      <span class="muted">as of ${new Date(d.as_of).toLocaleTimeString()}</span></p>
     <table class="livebook"><thead><tr>${head}</tr></thead><tbody>` +
    ordered.map(t => `<tr>${LIVE_COLS.map(c => `<td>${liveCell(t, c.k)}</td>`).join("")}</tr>`).join("") +
    "</tbody></table>";
}

async function loadLive() {
  try {
    const d = await fetchJSON("/api/live");
    lastLiveData = d;
    renderLiveBook(d);
  } catch (e) {
    const el = $("paper-open-content"); if (el) el.innerHTML = `<p class="muted">${e.message}</p>`;
  }
}

async function loadTrackRecord() {
  const el = $("track-record-content");
  if (!el) return;   // legacy panel removed; Track Record is now its own page
  try {
    const r = await fetchJSON("/api/track-record");
    if (!r.by_tier.length) {
      el.innerHTML = `<p class="muted">${r.open} simulated trades open, none closed yet.
        Win rates and average returns appear here as trades hit their target/stop or time out
        (usually a few days). The system tracks every proposal automatically — you don't have to buy anything.</p>`;
      return;
    }
    const ov = r.overall;
    let html = `<div class="scorecard">
      <div><span class="big">${num(ov.win_rate, 1)}%</span><br><span class="muted">overall accuracy</span></div>
      <div><span class="big ${ov.avg_return >= 0 ? "pos" : "neg"}">${pct(ov.avg_return, 1)}</span><br><span class="muted">avg return / trade</span></div>
      <div><span class="big">${r.closed}</span><br><span class="muted">closed</span></div>
      <div><span class="big">${r.open}</span><br><span class="muted">still open</span></div>
    </div>`;
    html += `<table><thead><tr>
      <th>Strategy</th><th>Confidence</th><th>Trades</th><th>Win rate</th>
      <th>Avg return</th><th>Avg win</th><th>Avg loss</th></tr></thead><tbody>`;
    html += r.by_tier.map(t => `<tr>
      <td>${t.strategy}</td>
      <td><span class="conf conf-${t.confidence}">${t.confidence}</span></td>
      <td>${t.n}</td>
      <td><strong>${num(t.win_rate, 1)}%</strong></td>
      <td class="${t.avg_return >= 0 ? "pos" : "neg"}">${pct(t.avg_return, 1)}</td>
      <td class="pos">${t.avg_win != null ? pct(t.avg_win, 1) : "-"}</td>
      <td class="neg">${t.avg_loss != null ? pct(t.avg_loss, 1) : "-"}</td>
    </tr>`).join("");
    html += "</tbody></table>";
    if (r.edges.length) {
      html += `<h3>Edge performance <span class="muted">(win rate of trades where each edge fired)</span></h3>`;
      html += `<table><thead><tr><th>Edge</th><th>Trades</th><th>Win rate</th><th>Avg return</th></tr></thead><tbody>`;
      html += r.edges.slice(0, 12).map(e => `<tr>
        <td>${e.edge}</td><td>${e.n}</td>
        <td><strong>${num(e.win_rate, 1)}%</strong></td>
        <td class="${e.avg_return >= 0 ? "pos" : "neg"}">${pct(e.avg_return, 1)}</td>
      </tr>`).join("");
      html += "</tbody></table>";
    }
    if (r.recent_closed && r.recent_closed.length) {
      html += `<h3>Recently closed trades <span class="muted">(how they actually finished)</span></h3>`;
      html += `<table><thead><tr><th>Symbol</th><th>Dir</th><th>Strategy</th><th>Confidence</th>
        <th>Given</th><th>Outcome</th><th>Return</th><th>Sector</th></tr></thead><tbody>`;
      html += r.recent_closed.map(t => `<tr>
        <td><strong>${t.symbol}</strong></td>
        <td>${t.direction === "short" ? '<span class="short-tag">SHORT</span>' : "long"}</td>
        <td>${t.strategy}</td>
        <td><span class="conf conf-${t.confidence}">${t.confidence || "-"}</span></td>
        <td class="muted">${(t.entry_date || "").slice(0, 10)}</td>
        <td class="${t.outcome === "win" ? "pos" : "neg"}">${(t.outcome || "").toUpperCase()}</td>
        <td class="${t.return_pct >= 0 ? "pos" : "neg"}">${pct(t.return_pct, 1)}</td>
        <td class="muted">${t.sector_name || ""}</td>
      </tr>`).join("");
      html += "</tbody></table>";
    }
    el.innerHTML = html;
  } catch (e) {
    el.innerHTML = `<p class="muted">${e.message}</p>`;
  }
}

async function loadAll() {
  await Promise.all([loadRegime(), loadAccounts(), loadPerformance(), loadSectors(),
    loadProposals(), loadLive(), loadTrades()]);
}

// The autonomous engine replaces the old manual "Run Scan": show its status.
async function loadEngineStatus() {
  const el = $("engine-status");
  if (!el) return;
  try {
    const s = await fetchJSON("/api/scheduler");
    el.classList.toggle("engine-live", !!s.running);
    el.classList.toggle("engine-off", !s.running);
    el.title = `Autonomous engine ${s.running ? "running" : "stopped"} · ` +
      `market ${s.market_open ? "open" : "closed"} · auto-execute ${s.auto_execute ? "ON" : "off (paper-safe)"}`;
    el.textContent = s.running
      ? (s.market_open ? "● Autonomous · scanning" : "● Autonomous · monitoring")
      : "○ Engine stopped";
  } catch (e) {
    el.textContent = "○ Engine status n/a";
  }
}

// ==================== Robinhood-style live dashboard ====================
const biasClass = (b) => b === "Bullish" ? "biastag-bull" : b === "Bearish" ? "biastag-bear" : "biastag-neut";
const gradeClass = (g) => (g && "ABCDF".includes(g)) ? "g-" + g : "g-U";
const gradeText = (g) => g === "UNGRADED" ? "UG" : (g || "—");
const gradeRank = (g) => ({ A: 5, B: 4, C: 3, D: 2, F: 1 }[g] || 0);
const archLabel = (a) => ({ trending_pullback_to_pivot: "Pullback", reversal: "Reversal", breakout_continuation: "Breakout" }[a] || (a || "—"));
const bandLabel = (b) => ({ "1-2 day": "1–2 Day", "1-2 week swing": "Swing", "intraday": "Intraday" }[b] || (b || ""));

let biasData = {};       // symbol -> bias-strip entry
let liveIndex = {};      // symbol -> /api/live trade
let algoIndex = {};      // trade id -> /api/log/algo trade
let lastAlgoData = { trades: [] };  // last /api/log/algo payload (for re-filtering)
let trackFilter = "all"; // Track Record filter: all | open | closed

async function refreshLiveIndex() {
  try {
    const d = await fetchJSON("/api/live");
    liveIndex = {};
    (d.trades || []).forEach(t => liveIndex[t.symbol] = t);
  } catch (e) { /* keep last */ }
}

async function loadBiasStrip() {
  const el = $("bias-strip"); if (!el) return;
  try {
    const d = await fetchJSON("/api/bias-strip");
    biasData = {};
    d.symbols.forEach(s => biasData[s.symbol] = s);
    el.innerHTML = d.symbols.map(m => `
      <div class="biascard ${m.symbol === 'SPY' ? 'spy' : ''}" onclick="openBias('${m.symbol}')">
        <div class="bc-top"><span class="bc-tk">${m.symbol}</span>
          <span class="biastag ${biasClass(m.bias)}">${m.bias}</span></div>
        <div class="bc-price">${price(m.price)}</div>
        <div class="bc-chg ${(m.session_pct ?? 0) >= 0 ? 'pos' : 'neg'}">${m.session_pct != null ? pct(m.session_pct, 2) : '—'} ${ageLabel(m.age_seconds)}</div>
        <div class="bc-lvls"><span class="lvl-up">above <b>${m.level_above != null ? num(m.level_above, 2) : '—'}</b></span>
          <span class="lvl-dn">watch <b>${m.level_below != null ? num(m.level_below, 2) : '—'}</b></span></div>
      </div>`).join("");
  } catch (e) { el.innerHTML = `<p class="muted">${e.message}</p>`; }
}

async function loadSectorBoard() {
  try {
    const [sectors, turning] = await Promise.all([
      fetchJSON("/api/sectors"), fetchJSON("/api/turning-sectors").catch(() => [])]);
    if (!sectors.length) { $("board-strong").innerHTML = '<p class="muted">No sector data yet.</p>'; return; }
    const sorted = [...sectors].sort((a, b) => (b.composite_score || 0) - (a.composite_score || 0));
    const turnSet = new Set(turning);
    const row = (s, tone) => {
      const up = (s.perf_1d || 0) >= 0;
      const lean = tone === 'nu' ? ` <span class="lean ${up ? 'lean-up' : 'lean-dn'}">${up ? '↑' : '↓'} leaning ${up ? 'up' : 'down'}</span>` : "";
      return `<div class="srow"><span class="sname">${s.sector_name}${lean}</span>
        <span class="sval ${tone === 'up' ? 'pos' : tone === 'dn' ? 'neg' : 'nu'}">${signed(s.composite_score)}</span></div>`;
    };
    $("board-strong").innerHTML = sorted.slice(0, 5).map(s => row(s, 'up')).join("");
    $("board-weak").innerHTML = sorted.slice(-3).reverse().map(s => row(s, 'dn')).join("");
    const watch = sorted.filter(s => turnSet.has(s.sector_name)).slice(0, 3);
    $("board-watch").innerHTML = watch.length ? watch.map(s => row(s, 'nu')).join("")
      : '<p class="muted">none turning right now</p>';
  } catch (e) { $("board-strong").innerHTML = `<p class="muted">${e.message}</p>`; }
}

// #7 Market Context: indices (SPY/QQQ/IWM) + VIX + breadth + calendar + news.
async function loadMarketOverview() {
  const tiles = $("market-tiles"); if (!tiles) return;
  try {
    const d = await fetchJSON("/api/market-overview");
    const asof = $("mkt-asof");
    if (asof) asof.textContent = d.as_of ? "as of " + new Date(d.as_of).toLocaleTimeString() : "";
    // indices are click-through like the bias cards -> fold into biasData
    (d.indices || []).forEach(m => biasData[m.symbol] = m);
    const idx = (d.indices || []).map(m => `
      <div class="mtile" onclick="openBias('${m.symbol}')">
        <div class="mt-tk">${m.symbol}</div>
        <div class="mt-val">${price(m.price)}</div>
        <div class="mt-sub ${(m.session_pct ?? 0) >= 0 ? 'pos' : 'neg'}">${m.session_pct != null ? pct(m.session_pct, 2) : '—'}</div>
      </div>`).join("");
    const vix = d.vix ? `<div class="mtile">
        <div class="mt-tk">VIX</div><div class="mt-val">${num(d.vix.level, 2)}</div>
        <div class="mt-sub ${d.vix.change <= 0 ? 'pos' : 'neg'}">${signed(d.vix.change, 2)} · ${d.vix.state}</div></div>` : '';
    const br = d.breadth ? `<div class="mtile">
        <div class="mt-tk">Breadth</div><div class="mt-val">${d.breadth.pct_up}% up</div>
        <div class="mt-sub muted">${d.breadth.advancers}▲ / ${d.breadth.decliners}▼ sectors</div></div>` : '';
    tiles.innerHTML = idx + vix + br || '<p class="muted">no data</p>';

    // "what's coming": economic events + held-name earnings, merged by date
    const cal = [
      ...(d.economic || []).map(e => ({ date: e.date, label: e.event, kind: 'econ' })),
      ...(d.earnings || []).map(e => ({ date: e.date, label: e.symbol + ' earnings', kind: 'earn' })),
    ].sort((a, b) => a.date.localeCompare(b.date)).slice(0, 8);
    const calEl = $("mkt-calendar");
    if (calEl) calEl.innerHTML = cal.length ? cal.map(e =>
      `<div class="cal-row"><span class="cal-date">${e.date.slice(5)}</span>
        <span class="cal-label ${e.kind === 'earn' ? 'cal-earn' : ''}">${e.label}</span></div>`).join("")
      : '<p class="muted">nothing scheduled</p>';

    const newsEl = $("mkt-news");
    if (newsEl) newsEl.innerHTML = (d.news || []).length ? (d.news || []).slice(0, 6).map(n =>
      `<div class="news-row">${n.url ? `<a href="${n.url}" target="_blank" rel="noopener noreferrer">${n.title}</a>` : n.title}
        ${n.provider ? `<span class="muted"> · ${n.provider}</span>` : ''}</div>`).join("")
      : '<p class="muted">no headlines</p>';
  } catch (e) { tiles.innerHTML = `<p class="muted">${e.message}</p>`; }
}

function setupChip(t) {
  return t.legacy ? '<span class="chip chip-legacy" title="opened before the grading path existed">legacy</span>'
    : `<span class="chip chip-arch">${archLabel(t.archetype)}</span>`;
}
function gradeBadge(t, small) {
  const sm = small ? ' sm' : '';
  if (t.legacy) return `<span class="grade${sm} g-L" title="legacy trade — pre-grading">L</span>`;
  return `<span class="grade${sm} ${gradeClass(t.process_grade)}" title="${t.process_grade || ''} — ${t.process_notes || ''}">${gradeText(t.process_grade)}</span>`;
}

function ideaRow(t) {
  const live = liveIndex[t.symbol];
  const lp = live ? live.live_price : null, pnl = live ? live.live_pnl_pct : null;
  // full trade at a glance: the plan (entry → stop / target) + the live line
  const planLine = `${price(t.entry_price)} → ${price(t.stop_loss)} / ${price(t.target_price)}`;
  const liveLine = lp != null ? ` · live ${price(lp)}${pnl != null ? ' ' + pct(pnl, 1) : ''}` : '';
  return `<div class="idea" onclick="openTrade(${t.id})">
    <span class="i-tk">${t.symbol}${t.direction === 'short' ? ' <span class="short-tag">▼</span>' : ''}</span>
    <div class="i-mid"><div class="i-chips">
        ${setupChip(t)}
        <span class="chip chip-tf">${bandLabel(t.timeframe_band)}</span>
        <span class="chip chip-strat">${t.strategy}</span>
        ${t.quality_score != null ? `<span class="chip chip-q">${num(t.quality_score, 1)}/10</span>` : ''}</div>
      <span class="i-sub muted">${planLine}${liveLine}</span></div>
    <div class="i-rr"><div class="v">${num(t.risk_reward, 1)}:1</div><div class="l">R:R</div></div>
    ${gradeBadge(t, false)}
  </div>`;
}

function renderIdeasFeed(d) {
  const el = $("ideas-feed"); if (!el) return;
  const open = (d.trades || []).filter(t => t.status === 'open')
    .sort((a, b) => gradeRank(b.process_grade) - gradeRank(a.process_grade) || (b.planned_rr || 0) - (a.planned_rr || 0));
  el.innerHTML = open.length ? open.map(ideaRow).join("")
    : '<p class="muted">No open algo trades yet — the engine opens them as setups qualify.</p>';
}

function renderTrackRecord(d) {
  const el = $("track-body"); if (!el) return;
  const trades = d.trades || [];
  const sm = $("track-summary");

  // Scorecards measure the FINISHED system only: legacy rows (opened before the
  // grading path existed) are shown in the table but excluded from the stats.
  const graded = trades.filter(t => !t.legacy);
  const closed = graded.filter(t => t.status === 'closed');
  const wins = closed.filter(t => t.outcome === 'win').length;
  const rVals = closed.map(t => t.r_multiple).filter(v => v != null);
  const avgR = rVals.length ? rVals.reduce((a, b) => a + b, 0) / rVals.length : null;
  const totalPnl = closed.reduce((a, t) => a + (t.pnl_usd || 0), 0);
  const winRate = closed.length ? 100 * wins / closed.length : null;
  const dist = { A: 0, B: 0, C: 0, D: 0, F: 0, UG: 0 };
  graded.forEach(t => { const g = t.process_grade === 'UNGRADED' ? 'UG' : t.process_grade; if (g in dist) dist[g]++; });
  const legacyN = d.legacy ?? trades.filter(t => t.legacy).length;

  const cards = $("track-cards");
  if (cards) cards.innerHTML = `
    <div class="scard"><div class="big">${graded.length}</div><div class="lbl">graded trades</div></div>
    <div class="scard"><div class="big">${winRate != null ? num(winRate, 0) + '%' : '—'}</div><div class="lbl">win rate (${closed.length} closed)</div></div>
    <div class="scard"><div class="big ${(avgR ?? 0) >= 0 ? 'pos' : 'neg'}">${avgR != null ? signed(avgR, 2) + 'R' : '—'}</div><div class="lbl">avg R-multiple</div></div>
    <div class="scard"><div class="big ${totalPnl >= 0 ? 'pos' : 'neg'}">${money(totalPnl, 0)}</div><div class="lbl">realized P&L</div></div>
    <div class="scard grades"><div class="gdist">
      ${['A', 'B', 'C', 'D', 'F', 'UG'].map(g => `<span class="gpill ${g === 'UG' ? 'g-U' : 'g-' + g}">${g} ${dist[g]}</span>`).join("")}
    </div><div class="lbl">process grades</div></div>`;

  const nOpen = trades.filter(t => t.status === 'open').length;
  const nClosed = trades.filter(t => t.status === 'closed').length;
  if (sm) sm.textContent = `${graded.length} graded · ${d.ungraded} ungraded` +
    (legacyN ? ` · ${legacyN} legacy (pre-grading, excluded from stats)` : '') + ' — autofills after each trade';

  // filter: all / open / closed
  const rows = trackFilter === 'all' ? trades : trades.filter(t => t.status === trackFilter);
  const fbtn = (label, key, n) =>
    `<button class="chip ${trackFilter === key ? 'on' : ''}" onclick="setTrackFilter('${key}')">${label} <span class="muted">${n}</span></button>`;
  const filterbar = `<div class="filterbar">
    ${fbtn('All', 'all', trades.length)}${fbtn('Open', 'open', nOpen)}${fbtn('Closed', 'closed', nClosed)}</div>`;

  if (!trades.length) { el.innerHTML = filterbar + '<p class="muted">No algo trades yet — rows appear here automatically as the engine takes trades.</p>'; return; }

  el.innerHTML = filterbar + `<table class="track"><thead><tr>
      <th>Date</th><th>Symbol</th><th>Setup</th><th>Band</th><th>Entry → Stop / Target</th>
      <th>R:R</th><th>Grade</th><th>Feedback</th><th>Outcome</th>
      <th class="pnlcol">R</th><th class="pnlcol">Return</th><th class="pnlcol">P&amp;L</th></tr></thead><tbody>` +
    rows.map(t => {
      const live = liveIndex[t.symbol], isOpen = t.status === 'open';
      // Outcome = Win/Loss for closed; a live tag for open
      const outcome = isOpen ? '<span class="tagopen">open</span>'
        : `<span class="${t.outcome === 'win' ? 'pos' : 'neg'}">${t.outcome === 'win' ? 'Win' : 'Loss'}</span>`;
      // Return %: closed uses realized return_pct; open shows the live P&L %
      const retPct = isOpen
        ? (live && live.live_pnl_pct != null ? `<span class="${live.live_pnl_pct >= 0 ? 'pos' : 'neg'}">${pct(live.live_pnl_pct, 1)}</span> ${ageLabel(live.age_seconds)}` : '<span class="muted">—</span>')
        : (t.return_pct != null ? `<span class="${t.return_pct >= 0 ? 'pos' : 'neg'}">${pct(t.return_pct, 1)}</span>` : '<span class="muted">—</span>');
      const rCell = isOpen || t.r_multiple == null ? '<span class="muted">—</span>'
        : `<span class="${t.r_multiple >= 0 ? 'pos' : 'neg'}">${signed(t.r_multiple, 2)}R</span>`;
      const pnlCell = isOpen || t.pnl_usd == null ? '<span class="muted">—</span>'
        : `<span class="${t.pnl_usd >= 0 ? 'pos' : 'neg'}">${money(t.pnl_usd)}</span>`;
      return `<tr class="jrow" onclick="openTrade(${t.id})">
        <td class="muted nowrap">${(t.entry_date || '').slice(0, 10)}</td>
        <td><strong>${t.symbol}</strong>${t.direction === 'short' ? ' <span class="short-tag">▼</span>' : ''}</td>
        <td>${t.legacy ? '<span class="chip chip-legacy">legacy</span>' : archLabel(t.archetype)}</td>
        <td class="muted">${bandLabel(t.timeframe_band)}</td>
        <td class="muted nowrap">${price(t.entry_price)} → ${price(t.stop_loss)} / ${price(t.target_price)}</td>
        <td>${num(t.risk_reward, 1)}:1</td>
        <td>${gradeBadge(t, true)}</td>
        <td class="feedback muted">${t.legacy ? '<span class="muted">— pre-grading —</span>' : (t.process_notes || '—')}</td>
        <td>${outcome}</td>
        <td class="pnlcol">${rCell}</td>
        <td class="pnlcol">${retPct}</td>
        <td class="pnlcol">${pnlCell}</td>
      </tr>`;
    }).join("") + "</tbody></table>";
}

function setTrackFilter(f) { trackFilter = f; renderTrackRecord(lastAlgoData); }

async function loadAlgo() {
  try {
    await refreshLiveIndex();
    const d = await fetchJSON("/api/log/algo");
    algoIndex = {};
    (d.trades || []).forEach(t => algoIndex[t.id] = t);
    lastAlgoData = d;
    renderIdeasFeed(d);
    renderTrackRecord(d);
  } catch (e) {
    const el = $("ideas-feed"); if (el) el.innerHTML = `<p class="muted">${e.message}</p>`;
  }
}

// ---- detail sheet ----
function showSheet() { $("detail-overlay").classList.add("open"); $("detail-sheet").classList.add("open"); }
function closeDetail() { $("detail-overlay").classList.remove("open"); $("detail-sheet").classList.remove("open"); }

function openBias(sym) {
  const m = biasData[sym]; if (!m) return;
  $("d-ticker").textContent = sym;
  $("d-price").textContent = price(m.price);
  const tag = $("d-tag"); tag.textContent = m.bias; tag.className = "biastag " + biasClass(m.bias);
  $("detail-body").innerHTML = `
    <div class="d-kv">
      <div class="cell"><div class="l">Stance</div><div class="v ${m.bias === 'Bullish' ? 'pos' : m.bias === 'Bearish' ? 'neg' : ''}">${m.bias} — conditional</div></div>
      <div class="cell"><div class="l">Session</div><div class="v ${(m.session_pct ?? 0) >= 0 ? 'pos' : 'neg'}">${m.session_pct != null ? pct(m.session_pct, 2) : '—'}</div></div>
      <div class="cell"><div class="l">Key level above ▲</div><div class="v">${m.level_above != null ? num(m.level_above, 2) : '—'}</div></div>
      <div class="cell"><div class="l">Key level below ▼</div><div class="v">${m.level_below != null ? num(m.level_below, 2) : '—'}</div></div>
    </div>
    <p class="muted" style="margin-top:12px">Conditional, not a forecast: constructive while it holds the lower level, cautious if it loses it.</p>
    <div class="d-block"><h4>Timeframe breakdown</h4>
      <div id="drill-body" class="muted">Reading 15m / 30m / 1h / 4h / daily…</div></div>`;
  showSheet();
  loadDrilldown(sym);
}

// #8 MAG-7 drill-down: bias per timeframe + a trade plan only when the real
// (compression + MACD-cross + pivot) confluence is there.
const MTF_ORDER = ["15m", "30m", "1h", "4h", "daily"];
async function loadDrilldown(sym) {
  const el = $("drill-body"); if (!el) return;
  try {
    const d = await fetchJSON(`/api/drilldown/${encodeURIComponent(sym)}`);
    const tfs = d.timeframes || {};
    const rows = MTF_ORDER.filter(tf => tfs[tf]).map(tf => {
      const r = tfs[tf];
      const cls = r.bias === 'Bullish' ? 'pos' : r.bias === 'Bearish' ? 'neg' : 'muted';
      const tags = (r.squeeze ? '<span class="mtf-tag">squeeze</span>' : '') +
        (r.macd_cross ? `<span class="mtf-tag">MACD ${r.macd_dir}-cross</span>` : `<span class="muted">MACD ${(r.macd || '').toLowerCase()}</span>`);
      return `<div class="mtf-row"><span class="mtf-tf">${tf}</span>
        <span class="mtf-bias ${cls}">${r.bias}</span><span class="mtf-tags">${tags}</span></div>`;
    }).join("");
    let plan;
    if (d.plan) {
      const p = d.plan;
      plan = `<div class="drill-plan ${p.direction === 'long' ? 'plan-long' : 'plan-short'}">
        <div class="dp-head">Trade plan · <strong>${p.direction.toUpperCase()}</strong> <span class="muted">(${p.trigger_tf} trigger)</span></div>
        <div class="plan3" style="margin-top:8px">
          <div class="p p-e"><div class="l">Entry</div><div class="v">${price(p.entry)}</div></div>
          <div class="p p-s"><div class="l">Stop</div><div class="v">${price(p.stop)}</div></div>
          <div class="p p-t"><div class="l">Target</div><div class="v">${price(p.target)}</div></div>
        </div>
        <div class="muted" style="margin-top:8px">R:R ${num(p.risk_reward, 1)}:1 · ${p.note}</div></div>`;
    } else {
      plan = '<p class="muted" style="margin-top:10px">No trade plan — the compression + MACD-cross + pivot confluence isn\'t there right now. Bias only (no manufactured trade).</p>';
    }
    el.classList.remove("muted");
    el.innerHTML = `<div class="mtf">${rows || '<p class="muted">no timeframe data</p>'}</div>${plan}` +
      (d.alpaca_enabled ? '' : '<p class="muted" style="margin-top:8px">Alpaca off — intraday timeframes may be limited.</p>');
  } catch (e) { el.innerHTML = `<p class="muted">${e.message}</p>`; }
}

function openTrade(id) {
  const t = algoIndex[id]; if (!t) return;
  const live = liveIndex[t.symbol];
  $("d-ticker").textContent = t.symbol + (t.direction === 'short' ? ' ▼' : '');
  $("d-price").textContent = live ? price(live.live_price) : price(t.entry_price);
  const tag = $("d-tag"); tag.textContent = (t.process_grade || '—') + " grade";
  tag.className = "biastag " + (gradeClass(t.process_grade) === 'g-U' ? 'biastag-neut' : 'biastag-bull');
  let flags = []; try { flags = JSON.parse(t.process_flags || "[]"); } catch (e) { }
  $("detail-body").innerHTML = `
    <div class="plan3">
      <div class="p p-e"><div class="l">Entry</div><div class="v">${price(t.entry_price)}</div></div>
      <div class="p p-s"><div class="l">Stop</div><div class="v">${price(t.stop_loss)}</div></div>
      <div class="p p-t"><div class="l">Target</div><div class="v">${price(t.target_price)}</div></div>
    </div>
    <div class="d-kv" style="margin-top:12px">
      <div class="cell"><div class="l">Setup</div><div class="v">${t.legacy ? 'legacy (pre-grading)' : archLabel(t.archetype)}</div></div>
      <div class="cell"><div class="l">Timeframe band</div><div class="v">${bandLabel(t.timeframe_band) || '—'}</div></div>
      <div class="cell"><div class="l">R:R</div><div class="v">${num(t.risk_reward, 1)}:1</div></div>
      <div class="cell"><div class="l">Quality</div><div class="v">${t.quality_score != null ? num(t.quality_score, 1) + '/10' : '—'}</div></div>
      <div class="cell"><div class="l">RS vs SPY</div><div class="v ${(t.rs_vs_spy ?? 0) >= 0 ? 'pos' : 'neg'}">${t.rs_vs_spy != null ? pct(t.rs_vs_spy, 1) : '—'}</div></div>
      <div class="cell"><div class="l">Process grade</div><div class="v">${t.legacy ? 'legacy' : (t.process_grade || '—') + (t.process_score != null ? ' (' + t.process_score + ')' : '')}</div></div>
      <div class="cell"><div class="l">Status</div><div class="v">${t.status}${t.outcome ? ' · ' + t.outcome : ''}${t.r_multiple != null ? ' · ' + signed(t.r_multiple, 2) + 'R' : ''}</div></div>
    </div>
    ${t.legacy ? '' : `<div class="d-block"><h4>Process notes</h4><p class="muted">${t.process_notes || '—'}</p>
      <div class="flagwrap">${flags.map(f => `<span class="flag">${f}</span>`).join("")}</div></div>`}
    <div class="d-block"><h4>Confluences</h4><p class="muted">${(t.edges_fired || '—').split(", ").join(" · ")}</p></div>
    ${t.reasoning ? `<div class="d-block"><h4>Rationale</h4><p class="muted">${t.reasoning}</p></div>` : ''}
    ${live ? `<div class="d-block"><h4>Live</h4><p>${price(live.live_price)} ${ageLabel(live.age_seconds)} ·
      <span class="${(live.live_pnl_pct ?? 0) >= 0 ? 'pos' : 'neg'}">${pct(live.live_pnl_pct, 1)}</span> ·
      to stop ${pct(live.dist_to_stop_pct, 1)} / to target ${pct(live.dist_to_target_pct, 1)}</p></div>` : ''}`;
  showSheet();
}

// ---- view switching ----
function currentView() {
  const el = document.querySelector(".navtab.active");
  return el ? el.dataset.view : "dashboard";
}
function switchView(v) {
  document.querySelectorAll(".navtab").forEach(t => t.classList.toggle("active", t.dataset.view === v));
  document.querySelectorAll(".view").forEach(s => s.classList.toggle("active", s.id === "view-" + v));
  if (v === "dashboard") { loadMarketOverview(); loadBiasStrip(); loadSectorBoard(); loadAlgo(); }
  else if (v === "track") { loadAlgo(); }
  else if (v === "sectors") { loadSectors(); }
  else if (v === "more") { loadAll(); }
}
document.querySelectorAll(".navtab").forEach(tab => tab.addEventListener("click", () => switchView(tab.dataset.view)));
$("detail-close").addEventListener("click", closeDetail);
$("detail-overlay").addEventListener("click", closeDetail);
document.addEventListener("keydown", e => { if (e.key === "Escape") closeDetail(); });

document.querySelectorAll(".tab").forEach(tab => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
    tab.classList.add("active");
    proposalView = tab.dataset.view;
    renderProposals();
  });
});

// initial paint: dashboard (default view) + engine status, and the detailed
// "More" panels in the background so switching to them is instant.
loadMarketOverview();
loadBiasStrip();
loadSectorBoard();
loadAlgo();
loadEngineStatus();
loadAll();

// Live refresh, no page reload: the active live view every ~6s, engine status
// every 15s, the detailed panels every 30s.
setInterval(() => {
  const v = currentView();
  if (v === "dashboard") { loadBiasStrip(); loadSectorBoard(); loadAlgo(); }
  else if (v === "track") { loadAlgo(); }
}, 6000);
setInterval(loadEngineStatus, 15000);
setInterval(() => { if (currentView() === "dashboard") { loadMarketOverview(); } }, 60000);
setInterval(() => { if (currentView() === "more") { loadLive(); } }, 5000);
setInterval(() => { if (currentView() === "more") { loadAll(); } }, 30000);
