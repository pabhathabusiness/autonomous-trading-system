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
      el.innerHTML = '<p class="muted">No sector data yet -- run a scan</p>';
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
    el.innerHTML = '<p class="muted">No pending proposals -- run a scan</p>';
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
        : '<p class="muted">No short-term momentum ideas cleared the filters this scan — run a scan, or there are no clean setups right now.</p>');
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

// Live paper-trade book: marks every open sim trade to Alpaca's real-time
// feed (live price, live P&L, RS-vs-SPY). Polled every ~5s; no page refresh.
async function loadLive() {
  const el = $("paper-open-content");
  try {
    const d = await fetchJSON("/api/live");
    const trades = d.trades || [];
    if (!trades.length) {
      el.innerHTML = '<p class="muted">No open simulated trades yet — run a scan.</p>';
      return;
    }
    const maxAge = Math.max(...trades.map(t => t.age_seconds ?? 0));
    const feed = d.alpaca_enabled
      ? `<span class="age ${maxAge < 90 ? "age-live" : "age-stale"}">${maxAge < 90 ? "🟢 LIVE" : "⚠ stale " + ageLabel(maxAge).replace(/<[^>]+>/g, "")}</span> Alpaca IEX`
      : '<span class="muted">Alpaca off — showing plan only</span>';
    const spy = d.spy || {};
    const bySector = {};
    for (const t of trades) (bySector[t.sector_name || "Unclassified"] ||= []).push(t);
    const sectors = Object.keys(bySector).sort();

    el.innerHTML =
      `<p class="muted">${d.open_count} open · ${d.priced_count} priced live · ${feed}
        · SPY ${price(spy.price)} ${spy.session_pct != null ? "(" + pct(spy.session_pct, 1) + " session)" : ""}
        <span class="muted">as of ${new Date(d.as_of).toLocaleTimeString()}</span></p>` +
      sectors.map(s => {
        const rows = bySector[s];
        return `<h4>${s} <span class="muted">(${rows.length})</span></h4>
          <table><thead><tr>
            <th>Symbol</th><th>Strategy</th><th>Given</th>
            <th>Plan (entry→stop/target)</th><th>Live</th><th>Live P&L</th><th>vs SPY</th>
          </tr></thead><tbody>` +
          rows.map(t => {
            const shortTag = t.direction === "short" ? ' <span class="short-tag">▼</span>' : "";
            return `<tr>
              <td><strong>${t.symbol}</strong>${shortTag}</td>
              <td>${t.strategy}</td>
              <td class="muted">${(t.entry_date || "").slice(0, 10)}</td>
              <td class="muted">${price(t.entry_price)} → ${price(t.stop_loss)} / ${price(t.target_price)}</td>
              <td>${price(t.live_price)} ${ageLabel(t.age_seconds)}</td>
              <td class="${(t.live_pnl_pct ?? 0) >= 0 ? "pos" : "neg"}">${pct(t.live_pnl_pct, 2)}</td>
              <td class="${(t.rs_vs_spy ?? 0) >= 0 ? "pos" : "neg"}">${t.rs_vs_spy != null ? pct(t.rs_vs_spy, 1) : "-"}</td>
            </tr>`;
          }).join("") + `</tbody></table>`;
      }).join("");
  } catch (e) {
    el.innerHTML = `<p class="muted">${e.message}</p>`;
  }
}

async function loadWatchlist() {
  const el = $("watchlist-content");
  try {
    const [watch, proposals] = await Promise.all([
      fetchJSON("/api/watchlist"),
      fetchJSON("/api/proposals?status=pending"),
    ]);
    if (!watch.length) {
      el.innerHTML = '<p class="muted">No names yet. Add tickers you believe have a catalyst — the system watches them for the squeeze + accumulation breakout footprint.</p>';
      return;
    }
    const coilBySym = {};
    for (const p of proposals) if (p.strategy === "coiling") coilBySym[p.symbol] = p;
    el.innerHTML = `<table><thead><tr><th>Ticker</th><th>Your note</th><th>Status</th><th></th></tr></thead><tbody>` +
      watch.map(w => {
        const c = coilBySym[w.symbol];
        const status = c
          ? `<span class="conf conf-${c.confidence}">🌀 COILING ${num(c.quality_score, 1)}/10</span> <span class="muted">trigger ${price(c.entry_price)}</span>`
          : '<span class="muted">watching…</span>';
        return `<tr>
          <td><strong>${w.symbol}</strong></td>
          <td class="muted">${w.note || ""}</td>
          <td>${status}</td>
          <td><button class="reject" style="padding:2px 8px" onclick="removeWatch('${w.symbol}')">✕</button></td>
        </tr>`;
      }).join("") + "</tbody></table>";
  } catch (e) {
    el.innerHTML = `<p class="muted">${e.message}</p>`;
  }
}

async function addWatch() {
  const sym = $("watch-symbol").value.trim().toUpperCase();
  const note = $("watch-note").value.trim();
  if (!sym) return;
  try {
    await fetchJSON(`/api/watchlist?symbol=${encodeURIComponent(sym)}&note=${encodeURIComponent(note)}`, { method: "POST" });
    $("watch-symbol").value = "";
    $("watch-note").value = "";
    await loadWatchlist();
  } catch (e) {
    alert(`Could not add ${sym}: ${e.message}`);
  }
}

async function removeWatch(sym) {
  try {
    await fetchJSON(`/api/watchlist/${encodeURIComponent(sym)}`, { method: "DELETE" });
    await loadWatchlist();
  } catch (e) {
    alert(`Could not remove ${sym}: ${e.message}`);
  }
}

async function loadTrackRecord() {
  const el = $("track-record-content");
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
    loadWatchlist(), loadProposals(), loadTrackRecord(), loadLive(), loadTrades()]);
}

$("scan-btn").addEventListener("click", async () => {
  const status = $("scan-status");
  status.textContent = "Scanning...";
  $("scan-btn").disabled = true;
  try {
    const result = await fetchJSON("/api/scan", { method: "POST" });
    status.textContent = `Scan complete: ${JSON.stringify(result.proposals)}`;
    await loadAll();
  } catch (e) {
    status.textContent = `Scan failed: ${e.message}`;
  } finally {
    $("scan-btn").disabled = false;
  }
});

$("watch-add-btn").addEventListener("click", addWatch);
$("watch-symbol").addEventListener("keydown", e => { if (e.key === "Enter") addWatch(); });

document.querySelectorAll(".tab").forEach(tab => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
    tab.classList.add("active");
    proposalView = tab.dataset.view;
    renderProposals();
  });
});

loadAll();
setInterval(loadAll, 30000);
// live paper-trade book refreshes every 5s (no full page reload)
setInterval(loadLive, 5000);
