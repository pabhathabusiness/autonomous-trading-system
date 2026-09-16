# Market Intelligence Schema (DRAFT)

**Status:** DRAFT for owner review — NOT wired to production. Companion
doc to `TOP10_UX_SPEC.md`. Defines the *data contract* for the eventual
Market page + the inputs the Top 10 regime band pulls from, so both can
be built off a stable surface.

**Scope:** the shape and semantics of the data that answers "what is the
market doing right now, and does the playbook currently permit new
risk?". Does not specify UI (the Market page UX will be its own spec
after droplet sync). Does not modify any existing file.

**Naming convention:** every field in this schema is a *decision input*.
If a field cannot be pointed at a playbook rule or a card decision, it
does not belong here.

---

## 1. Top-level shape

Aspirational endpoint contract: `GET /api/market/intel` returns one
JSON object with the four sections below. Every section carries its own
`refresh_ts` so a client can render "stale" independently per section.

```
{
  "regime": { ... },       // § 2
  "breadth": { ... },      // § 3
  "vol": { ... },          // § 4
  "correlation": { ... }   // § 5
}
```

The Top 10 regime band (`TOP10_UX_SPEC.md` § 3.1) reads only `regime`
plus a portfolio-state field owned by a separate endpoint. Every other
section on this page feeds the Market view and the Research view but is
optional for Top 10.

## 2. `regime` — SPY classification

Governs the playbook's HS-A gate and MIXED-regime rules.

```
regime: {
  classification: "BULLISH" | "BEARISH" | "MIXED" | "UNKNOWN",
  as_of: iso8601,
  inputs: {
    spy_close: float,
    spy_sma20: float,
    spy_sma50: float,
    ret_5d: float,
    sma50_slope: float,
    session: "PREMARKET" | "REGULAR" | "AFTERHOURS" | "CLOSED"
  },
  rule_hits: {
    bullish: bool,      // all 4 BULLISH conditions
    bearish: bool,      // all 4 BEARISH conditions
    mixed: bool         // neither BULLISH nor BEARISH
  },
  confidence: "HIGH" | "MEDIUM" | "LOW",
  history_7d: [
    { date: yyyy-mm-dd, classification: enum }
  ]
}
```

**Rules (frozen at preregistration in `schwab_hypothesis_spy_load.py`):**

- BULLISH ⇔ `spy_close > sma20 ∧ spy_close > sma50 ∧ ret_5d > 0 ∧ sma50_slope ≥ 0`
- BEARISH ⇔ symmetric with `<` and `< 0` and `≤ 0`
- MIXED ⇔ neither BULLISH nor BEARISH holds
- UNKNOWN ⇔ inputs missing / stale

**Never** override the rule with a discretionary "feels bullish" label.
If the rule outputs MIXED, the field says MIXED even if the owner
disagrees.

**`confidence`** downgrades to LOW when any input is stale > 30 min
during regular session or > 4h off-session.

## 3. `breadth` — advance/decline + participation

Used for context on the Market page and as an optional playbook R
hypothesis input (not currently a hard gate).

```
breadth: {
  as_of: iso8601,
  advancing: int,        // NYSE + NASDAQ combined
  declining: int,
  unchanged: int,
  ad_ratio: float,       // advancing / declining
  new_highs: int,        // 52w
  new_lows: int,         // 52w
  pct_above_sma50: {     // % of tracked universe
    universe: "SP500" | "R2000" | "COMPOSITE",
    value: float
  },
  sector_leaders: [
    { sector: string, ret_1d: float, ret_5d: float }
  ]
}
```

Sector labels use the same SECTOR_MAP taxonomy hand-coded in
`schwab_hypothesis_spy_load.py` (Semi mega-cap, Consumer tech, Energy,
Financials, etc.) so the sector leader list can be joined to the
correlation cluster labels on Top 10 cards without re-mapping.

## 4. `vol` — volatility state

Used for D-11 option-value estimator inputs and for a soft caution
band on the Market page.

```
vol: {
  as_of: iso8601,
  vix: float,
  vix_5d_change: float,
  vix_state: "LOW" | "NORMAL" | "ELEVATED" | "STRESSED",
  term_structure: "CONTANGO" | "BACKWARDATION" | "FLAT",
  iv_rank: {
    // for the option-universe currently watched
    median: float,
    p90: float
  }
}
```

**`vix_state` thresholds (preregister here before ever using them as a
gate):**

- LOW ≤ 13
- 13 < NORMAL ≤ 20
- 20 < ELEVATED ≤ 30
- STRESSED > 30

These are current placeholders; do not gate on `vix_state` until the
threshold set is evidence-backed on the owner's trade history the way
`schwab_hypothesis_spy_load.py` grounds the SPY thresholds.

## 5. `correlation` — cluster state of the tracked universe

Governs the Top 10 cluster tag + the effective-bet-count computation.

```
correlation: {
  as_of: iso8601,
  window_days: 20,       // rolling window for pairwise r
  clusters: [
    {
      label: string,     // e.g. "Semi mega-cap long"
      tickers: [string],
      centroid_ret_5d: float,
      internal_r_median: float   // median pairwise r within cluster
    }
  ],
  pairs_at_or_above_threshold: int,   // pairs with r >= 0.6
  threshold_r: 0.6,
  method: "PEARSON_LOG_RETURNS"
}
```

The `label` field is taken from SECTOR_MAP plus a direction inferred
from centroid return sign — the classifier is purely mechanical. The
consumer (Top 10, portfolio-load, Market) reads `label` as an opaque
string.

## 6. Freshness / staleness policy

Each section carries an `as_of`. A client is required to render
"stale" (not to hide, not to silently retry) if any of:

- section is > 15 min stale during REGULAR session
- > 60 min stale during PREMARKET / AFTERHOURS
- > 24h stale when CLOSED

Rendering a "current" number on stale data is the primary failure
mode we are guarding against — cf. `TOP10_UX_SPEC.md` § 3.1 stale
handling.

## 7. Error / missing-data policy

Every numeric field is `float | null`. Every enum is
`enum | "UNKNOWN"`. The client must handle `null` and `UNKNOWN`
explicitly — never zero-fill, never assume the previous value carries
over silently.

## 8. Instrumentation

Each `/api/market/intel` response includes a `_meta` block (not shown
above to keep the shape readable) with:

```
_meta: {
  request_id: uuid,
  sources: {
    spy: "alpaca_iex" | "yfinance" | "fallback",
    breadth: "wsj_scrape" | "provider_X" | ...,
    vix: "cboe" | "yfinance" | ...,
    correlation: "internal_daily_bars"
  },
  computed_at: iso8601,
  compute_ms: int
}
```

This is required so that when the Top 10 card renders "regime = MIXED,
confidence = LOW," the owner can trace whether the SPY inputs came
from the primary or a fallback source. The Alpaca-vs-yfinance switch
in particular has been a silent failure mode historically.

## 9. What this schema is NOT

- Not a news feed (belongs on One Read).
- Not a scanner output (belongs on Scanner).
- Not a P&L feed (belongs on Dashboard).
- Not economic-calendar data (separate; may live under the Market page
  as a *sibling* section but not inside this schema).
- Not sentiment / social — deliberately excluded. If it ever enters,
  it does so as an explicit new section with its own confidence
  policy.

## 10. Reconciliation with live droplet (post-sync)

Once the droplet checkout lands:

1. Diff whatever the live "Market" (or its precursor) currently
   returns against § 2-§ 5.
2. For every field the live source has that this schema does not:
   decide "add to schema" or "reject as decoration."
3. For every field this schema has that the live source lacks: decide
   "wire it up now" or "defer with a stub."
4. Freeze the reconciled schema before writing any new UI against it.

## 11. Open questions

1. **Should breadth pull an official provider or scrape WSJ?** —
   scraping is fragile; a paid feed is cleaner. Owner decides.
2. **Do we include a real-money "risk-on / risk-off" scalar?** —
   default here is NO; it invites narrative overrides.
3. **Where do futures / overnight session fit?** — deferred; premarket
   handling stays coarse ("session = PREMARKET, confidence = LOW") until
   there is evidence a finer breakdown improves owner decisions.

---

**Related docs:**

- `TOP10_UX_SPEC.md` — consumer of § 2 and § 5.
- `PLAYBOOK_v2.1.1.md` — playbook rules that consume regime + cluster.
- `research/schwab_hypothesis_spy_load.py` — source of truth for
  the SPY classification rules encoded in § 2.
- `research/schwab_mixed_correlation.py` — source of truth for the
  correlation-cluster methodology in § 5.
