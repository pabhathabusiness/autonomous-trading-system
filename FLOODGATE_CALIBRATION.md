# Floodgate calibration log — MIN_COVERAGE=0.55 + turnaround over-representation

Two items logged (not fixed) before B1+B3, per request. Measured against the
live 1068-name universe on the server (`data/trading_system.db`), 2026-07-12.

---

## Item 1 — MIN_COVERAGE=0.55 is an unmeasured magic number. Characterize it.

### Universe-wide DATA availability per edge family (N=1068)

| family | available | pct | note |
|---|---:|---:|---|
| volume | 1068 | 100.0% | OHLC — always present |
| compression | 1060 | 99.3% | OHLC |
| float | 1058 | 99.1% | shares-outstanding proxy |
| structure | 1056 | 98.9% | OHLC/demand-trend |
| trend | 1056 | 98.9% | OHLC |
| sector | 1068 | 100.0% | system panel |
| **fundamental** | **1013** | **94.9%** | **well-fetched — NOT under-fetched** |
| **catalyst** | **76** | **7.1%** | Finnhub news; rate-limit starved |
| **insider** | **0** | **0.0%** | Finnhub insider-transactions; fully starved |

### Verdict: the floor is currently silencing ZERO real triggers.

Per-lane, on candidates (eligible AND gate-pass):

| lane | candidates | coverage<0.55 | **silenced_floor** | silenced_reqfund | fires |
|---|---:|---:|---:|---:|---:|
| reversal | 0 | 0 | 0 | 0 | 0 |
| breakout | 0 | 0 | 0 | 0 | 0 |
| compression | 844 | 8 | **0** | 0 | 3 |
| emerging_strength | 890 | 12 | **0** | 0 | 0 |
| hidden_value | 740 | 47 | **0** | 0 | 4 |
| turnaround | 740 | 47 | **0** | 0 | 7 |

`silenced_floor` = names that *would* have fired (composite≥6.5, ≥3 non-sector
families) but were blocked by coverage<0.55. It is **0 for every lane**. Same for
`silenced_reqfund` (require_available:fundamental). **The 0.55 floor and the
fundamental-required guard are, on today's universe, catching nothing** — every
name they silence has a weak chart too and would not have fired anyway.

### Why the floor looks "free": insider is 100% dark, so modal coverage is ~0.7

For hidden_value/turnaround the **modal coverage is ~0.7, not ~1.0** — because
insider (weight 2.5/≈12, ~21% of the lane) is absent on *every* name and catalyst
on 93%. So the typical value-name already runs with its two thesis-defining edges
excluded from the denominator, sitting at cov≈0.7. The floor only bites when
fundamental *also* drops (the ~47 names at 94.9%→missing), and those names score
too low to fire regardless.

**So: fundamentals are NOT under-fetched (94.9%). The floor is a correct, currently-
inert safety net.** The require_available:fundamental guard is the one doing the real
semantic work (proven by the synthetic worst-case where a fundamental-less name had
a strong enough chart to reach 6.5); it just happens to be redundant with the
composite math on *this* universe.

### The real finding this surfaces (flagged for investigation, not fixed now)

**insider = 0.0% and catalyst = 7.1% across the entire universe.** Both are wired
(`fh.insider_transactions` → `insider_score`; `fh.company_news` → `classify_news`)
but starved by the Finnhub free-tier rate limit during the 1068-name bulk build —
news itself only reached 76/1068, and insider is last in the per-symbol call queue,
so it gets nothing. The value lanes weight insider at ~21% and catalyst at 4–17%,
so **hidden_value/turnaround are currently scoring half-blind — their catalyst and
insider edges never contribute.** This is the genuine "floor masking under-fetched
data" risk the review asked about — except the under-fetched families are insider
and catalyst, not fundamental. **Before either value lane graduates anything, raise
insider/catalyst fetch coverage (staggered fetch / higher budget / on-demand enrich
of trigger candidates), or explicitly down-weight the always-dark edges.**

---

## Item 2 — 7 of 12 triggers are `turnaround`. Loosest gates, or real?

### Funnel (gate-less lanes; identical eligibility for the two value lanes)

| lane | eligible | cov/req pass | composite≥6.5 | +3 families (FIRE) |
|---|---:|---:|---:|---:|
| turnaround | 740 | 693 | **7** | 7 |
| hidden_value | 740 | 693 | 5 | 4 |
| compression | 844 | 836 | 3 | 3 |
| emerging_strength | 890 | 878 | 0 | 0 |

### It is NOT a looser gate — none of these four lanes has a gate.

Only `reversal` and `breakout` have hard gates. turnaround, hidden_value,
compression, emerging_strength are all gate-less; they rely purely on
composite≥6.5 + ≥3 families + coverage + require. turnaround and hidden_value have
the **identical** eligibility+coverage funnel (740→693). The divergence is entirely
at the composite step (7 vs 5).

### Why turnaround over-fires: its dark edges renormalize onto fund+trend.

- turnaround weights: fund 3.0, **catalyst 2.0, insider 2.5**, trend 1.5, … (den_all 12.0).
- With insider+catalyst dark (the universal case), it drops **4.5/12 = 37.5%** of its
  weight, and the composite renormalizes onto its residual denominator (7.5) —
  concentrated on fundamental+trend.
- hidden_value drops only insider+catalyst = 3.0/11.5 (its catalyst weight is 0.5,
  not 2.0), leaving a larger residual denominator (8.5), so the same fund+trend
  scores get a smaller lift.

**Conclusion: turnaround is over-represented as an artifact of its two thesis-
defining edges (catalyst, insider) being 100%/93% dark.** With those edges gone, its
composite collapses onto the generic fundamental+trend signal that hidden_value also
uses, and its smaller residual denominator tips more names over 6.5. The 7 names are
real fundamental+trend setups (all have fundamental data), but they are NOT verified
turnarounds in the thesis sense (catalyst + insider accumulation ahead of a
re-rating) — because the system cannot currently see catalyst or insider. This is the
same root cause as Item 1: **fix insider/catalyst fetch coverage before trusting the
turnaround/hidden_value split.**

---

## Net

Both guards (0.55 floor, require-fundamental) are correct and doing no harm today.
The number to chase is not the floor — it is the **0% insider / 7% catalyst fetch
coverage** that leaves the two fundamental-thesis lanes half-blind and inflates
turnaround. Logged for a dedicated fetch-coverage task; not touched here.
