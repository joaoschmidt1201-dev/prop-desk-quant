# Batman Backtest Pipeline — Playbook & Skill Seed

> How the desk runs **CZ's "Batman 1DTE" (dual OTM butterfly)** backtests on QuantConnect
> *autonomously* (Claude drives the cloud, no manual log pastes) and lands the results in the
> desk app for CZ. Captures the architecture, the hard-won gotchas, the findings, and exactly
> how to add a new scenario. This doc is meant to seed a future `/batman-backtest` skill.

Charter (scope/spec): `context/0DTE strategies/PROJECT_qc_backtest_scope.md`
Strategy framework (Coach Ernie): memory `project_zerodte_butterfly_playbook.md`

---

## 1. What "Batman" is (the strategy under test)
- **Structure:** a **call butterfly + a put butterfly**, each `+1 / -2 / +1`, both OTM (calls above
  spot, puts below). Looks like a bat silhouette → "Batman".
- **Underlying:** SPXW (cash-settled European, PM-settled), 1-minute resolution.
- **Entry:** 15:45 ET. **1DTE** = enter today for **next day's** expiry (also tested 0DTE, weekly).
- **Width by VIX (CZ/Ernie table):** VIX<17 → 20-30 · 17-25 → 30-40 · 25-32 → 40-50 · >32 → 50+.
- **Stop:** none. Max loss = the debit paid. "Manage risk, not profit" — losers run to expiry.
- **The thesis under test:** that a profit-target (close at X% of debit) and/or a VIX regime filter
  turns this into positive expectancy.

## 2. The 3 backtests currently in the app — what differs (it's the STRIKE PLACEMENT)
All three are 1DTE, full span 2022-06-20 → 2026-05-13, hold-to-expiry, $100k base.

| App id | Width chosen by | Center (short strikes) placed by | Net | WR |
|---|---|---|---|---|
| `batman-1dte-debit` **(faithful CZ)** | **VIX table** | strike where **debit ≈ 5%** of width | **−$39,421** | 19% |
| `batman-1dte-delta` | VIX table | each side at **~0.15 delta** (captures skew) | −$45,940 | 44% |
| `batman-1dte-debit-search` (baseline) | **widest** wing under the debit cap (not the table) | by debit | −$66,118 | 21% |

- **`debit` is THE canonical CZ spec** — anchor everything to it.
- `delta` ends with a much fatter real debit (~19%, not 5%) and a different VIX profile.
- `debit-search` was the early exploratory run; the width-search pushed wings to the max (60) → worst.

## 3. Findings so far (authoritative — these come from QC runtime stats / equity, not the blotter)
- **The whole loss lives in mid-vol.** Faithful 1DTE: VIX 22-32 ≈ −$33.9k is essentially the entire
  loss; VIX<15 (+$6.9k) and 17-22 (+$1.1k) are *positive*. Edge exists in low/mid vol; high-mid vol kills it.
- **Profit targets make it WORSE.** Hold −$39.4k > +50% −$55.5k > +100% −$56.4k > +200% −$59k. The TP
  raises win rate (tp100 WR 54% vs hold 19%) but **truncates the fat-tail winners that pay for
  everything**. → refutes CZ's "edge is in the management/TP" thesis; the fat tail IS the edge.
- **Trust level:** aggregates & per-VIX/per-year splits are reliable (reconcile to QC equity).
  A single trade's absolute $ is approximate (see §6 calibration).

## 4. Architecture (5 pieces)
1. **Engine** `backtests/quantconnect/batman_1dte_v1.py` — parametrized via `self.get_parameter(...)`:
   `structure` (0DTE|1DTE|weekly_mon_fri|weekly_fri_fri), `placement_mode` (debit|delta),
   `width_mode` (vix_table|debit_search), `tp_close_frac` (none|0.5|1.0|2.0 — **executes** the fly close
   at +X% of debit), `symmetry`, `target_delta`, `target_debit_frac`, `start_date`, `end_date`, `run_tag`.
   Emits rich **runtime statistics** (net by VIX bucket, by year, hold-vs-TP, WR, debit_frac, width) —
   this is the only export-safe channel on a non-institutional account.
2. **Sweep driver** `scripts/batman_sweep.py` — runs the GRID sequentially on QC cloud: write
   `config.json` → `lean cloud push` → `lean cloud backtest` → poll `/backtests/read` until done → read
   runtimeStatistics → save to `~/qc_batman/sweep_results.json`. Resilient: skips done, retries errors.
3. **Exporter** `scripts/batman_export_app.py` — pulls `closedTrades` per backtest via API, groups the 6
   legs by `entryTime` = 1 Batman, reconstructs per-trade P&L, calibrates to QC equity, writes the app
   schema CSVs to `reports/batman_backtest_app/<tag>/{trades,daily}.csv`.
4. **App API** `apps/api/main.py` — dynamic registry scans `reports/batman_backtest_app/`; `kind="batman"`,
   `multiplier=1`. KPIs incl. `yearly_breakdown` + `vix_breakdown` (CZ regimes). Batman close-rule =
   Hold only (TP targets are separate executed backtests). VIX entry filter enabled.
5. **App web** `apps/web/src/components/backtests/backtest-detail.tsx` — `YearlyBreakdownCard` +
   `VixBreakdownCard` (regime table) + trade inspector. Deploys via push→Vercel.

## 5. ⚠️ Gotchas discovered the hard way (READ BEFORE TOUCHING)
- **Margin bug (−34%/−66% fake losses):** legging in with 6 separate market orders → QC charged
  naked-short margin on the centers and corrupted the whole post-2024 span. **FIX:** enter via
  `OptionStrategies.butterfly_call` / `butterfly_put` combos (recognized defined-risk). Requires
  **exactly equidistant** strikes — `make()` rejects non-equidistant; `force_wing` makes the put inherit
  the call width for symmetry. Validated by a Nov-2024 gate (zero margin errors).
- **ObjectStore export is INSTITUTIONAL-ONLY** on our plan → `lean cloud object-store get` is blocked,
  and **backtest logs are NOT in the API.** Export-safe channels = (a) `runtimeStatistics`,
  (b) `totalPerformance.closedTrades`. Design every diagnostic around those two.
- **`closedTrades.profitLoss` is WRONG for ITM expiries** (ignores cash-settlement → shows WR 0% /
  −560k). **FIX:** recompute payoff from strikes + SPX close at expiry; only trust `profitLoss` for legs
  that were closed *early* (exitPrice > 0, i.e. a real TP round-trip).
- **`lean cloud backtest` → "Invalid credentials" is a LIE when the single free node is busy.** Free tier
  = 1 backtest node. If a prior/orphaned run is "In Progress", new submissions fail with a misleading
  auth error. **FIX:** `wait_node_free()` polls `/backtests/list` for any "In Progress" before submitting.
- **External SPX daily data in this network:** stooq (needs apikey now), yfinance (rate-limited), FRED
  (RemoteDisconnected) all FAIL. **Use the Yahoo chart endpoint**
  `query1.finance.yahoo.com/v8/finance/chart/%5EGSPC?range=5y&interval=1d` (stdlib, not bulk-rate-limited;
  same pattern as `apps/api/live_spot.py`). Cached to `data/cache/spx_daily.parquet`.

## 6. The calibration (what "P&L reconstructed (settlement payoff) calibrated to QC equity" means)
The per-trade $ is **reconstructed** (payoff from strikes + SPX close, since the blotter is blocked),
then every trade's pnl is scaled by `factor = QC_net / reconstructed_net` so the app total **equals the
authoritative QC equity exactly**. The factor is > 0, so it preserves each trade's **sign** (WR, win/loss
labels, in-range) and the **distribution shape** — only the absolute magnitude is nudged (recon uses the
daily SPX close as the settlement ref vs QC's intraday settle). **Verdict: trustworthy for aggregates,
WR, per-VIX and per-year splits; treat a single trade's exact dollar as ±a few %.**

## 7. HOW TO ADD A SCENARIO (the repeatable loop)
1. Add `(tag, overrides)` to `GRID` in `scripts/batman_sweep.py` (only **structural** axes — VIX/close-rule
   are slices of one run, not separate runs).
2. `python scripts/batman_sweep.py` (idempotent — skips tags that already have `runtime`).
3. `python scripts/batman_export_app.py` → writes the app CSVs.
4. Add a label to `_BATMAN_LABELS` in `apps/api/main.py` (English, always).
5. `git add reports/batman_backtest_app apps/... && git commit && git push` → Render+Vercel redeploy →
   appears in the app (registry is dynamic).

## 8. Wave 2 (after CZ sees v1)
Weekly TP marking (currently only marks expiry day, not intermediate days), entry-time sweep, 1-SD
placement, a TA gate, bull/bear fly switching, strict OOS holdout. Each is **one variable at a time**
(anti-overfit) and mostly a slice of an existing run, not a new QC run.

## Infra quick-ref
- QC project "Fat Violet Hippopotamus", cloud-id **27848355**, org `1f97d316a4d53242e929726971860505`,
  workspace `~/qc_batman`. Auth: `lean login` (token never in chat). HMAC API = `sha256(token:ts)` Basic.
- API helpers: `~/lean_qc/_rs.py <bid>` (runtime stats), `_bt.py`, `_ordsum.py`.
- App API (Render): `https://prop-desk-dashboard-api.onrender.com` · frontend on Vercel · both from
  GitHub `main` (monorepo). **Pushing to main is the deploy mechanism.**
- 🔴 Red line: never connect to a broker to execute live orders. Backtest/research only.
