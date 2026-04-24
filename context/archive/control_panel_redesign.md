# Control Panel Redesign

## Objective

Design a professional Google Sheets control panel that:

- gives Cristiano a clean executive view of the desk,
- preserves Joao's operational control,
- keeps Make automations simple and robust,
- supports AI export and post-trade analysis,
- scales without turning every new trade into a manual layout exercise.

The current workbook already proves the workflow. The redesign should keep the useful logic and replace the fragile structure.

## Design Principles

1. One trade = one row in the master registry.
2. One snapshot = one row in the snapshot log.
3. One event = one row in the event log.
4. Visible tabs are for reading and decisions.
5. Hidden tabs are for automation and normalization.
6. No business-critical logic should depend on a fixed column block per trade.
7. Every trade must have a stable `trade_id`.
8. The Google Sheet must be shareable with Cristiano without exposing admin clutter.

## Target Workbook Structure

### Visible Tabs

1. `Dashboard`
   Executive cockpit for Cristiano.

   Main modules:
   - Active trades
   - Open PnL
   - Realized MTD
   - Win rate 90D
   - Net delta
   - Open risk
   - Next expiries
   - PnL by month chart
   - Open trades by book
   - Setup performance
   - Recent action feed

2. `Trade Monitor`
   Daily operational grid for active trades.

   Recommended columns:
   - trade_id
   - book
   - status
   - trade_name
   - setup_family
   - underlying
   - open_dt
   - expiry_dt
   - dte_current
   - net_credit
   - max_profit
   - max_loss
   - current_pnl
   - realized_pnl
   - current_delta
   - underlying_price
   - vix
   - last_snapshot_ts
   - optionstrat_url

3. `Active Trades`
   Cleaner filtered view for open trades only.

4. `Closed Trades`
   Review table with post-trade fields.

   Recommended extra columns:
   - close_dt
   - close_reason
   - pnl_final
   - pnl_pct_max_profit
   - max_drawdown
   - best_pnl_seen
   - leak_tag
   - strength_tag
   - review_status

5. `Performance`
   Historical analytics layer.

   Suggested sections:
   - Realized PnL by month
   - Win rate by setup family
   - Avg PnL by underlying
   - Avg hold time by setup
   - Open vs closed distribution
   - PnL distribution buckets

6. `AI Export`
   Controlled area for exporting desk data to LLM workflows.

   Suggested functions:
   - one selected trade summary
   - latest snapshot summary
   - prompt-ready trade narrative
   - tabular export area
   - leak review export area

7. `Playbook`
   Compact, polished operational doctrine.

8. `Ops Control`
   Joao-only operational tab.
   This is still visible in the base file, but can be hidden in Cristiano's shared copy if desired.

### Hidden Tabs

1. `db_trade_registry`
   Master record. One row per trade.

2. `db_trade_legs`
   One row per leg.

3. `db_snapshots`
   One row per snapshot pull.

4. `db_events`
   One row per state change or manual note.

5. `db_import_queue`
   URLs detected by Make before final registry insertion.

6. `db_make_control`
   Control values for automations.

7. `dim_lookups`
   Status lists, books, sleeves, setups, underlyings, event types.

## Data Model

### `db_trade_registry`

Recommended columns:

- `trade_id`
- `book`
- `owner`
- `sleeve`
- `status`
- `trade_name`
- `setup_family`
- `setup_variant`
- `underlying`
- `optionstrat_url`
- `open_dt`
- `expiry_dt`
- `dte_open`
- `dte_current`
- `contracts`
- `net_credit`
- `max_profit`
- `max_loss`
- `open_underlying`
- `soll_low_be`
- `soll_up_be`
- `ist_low_be`
- `ist_up_be`
- `current_pnl`
- `realized_pnl`
- `current_delta`
- `tags`
- `month_bucket`
- `notes`
- `ai_ready`
- `last_snapshot_ts`

### `db_trade_legs`

Recommended columns:

- `trade_id`
- `leg_no`
- `action`
- `qty`
- `option_type`
- `strike`
- `expiry_dt`
- `delta_open`

### `db_snapshots`

Recommended columns:

- `snapshot_ts`
- `trade_id`
- `snapshot_slot`
- `pnl_open`
- `pnl_realized`
- `delta`
- `underlying_price`
- `vix`
- `regime_tag`
- `dist_soll_low_pct`
- `dist_soll_up_pct`
- `inside_tent_flag`
- `note`

### `db_events`

Recommended columns:

- `event_id`
- `trade_id`
- `event_ts`
- `event_type`
- `actor`
- `field_name`
- `old_value`
- `new_value`
- `note`

## UI Direction

### Executive UI

The shared sheet for Cristiano should feel like a trading control panel, not a raw spreadsheet.

UI choices:

- dark navy header band
- off-white working canvas
- muted gridlines
- high contrast KPI cards
- restrained accent colors:
  - green for realized gains
  - red for drawdown/risk
  - amber for pending attention
  - steel blue for neutral data
- large typography only on section headers and KPIs
- operational tables kept flat and clean

### Interaction Pattern

Cristiano should open the file and immediately see:

1. whether the desk is winning or bleeding,
2. how many trades are still active,
3. where the major open exposures are,
4. which trade needs attention next,
5. how the current month compares with prior months.

Joao should open the same file and immediately see:

1. data freshness,
2. automation health,
3. registry integrity,
4. snapshot continuity,
5. AI export readiness.

## Automation Architecture

### Current Make Logic to Preserve

1. Detect new URLs where trade status is `NEW`.
2. Scrape OptionStrat and append a normalized trade record.
3. Pull PnL and Delta twice daily for active trades.

### Redesign Recommendation

Instead of reading multiple visual tabs directly, Make should prefer:

1. `db_import_queue`
2. `db_trade_registry`
3. `db_snapshots`

Visible sheets should become outputs, not system-of-record inputs.

### Recommended Control Keys

Store in `db_make_control`:

- `last_new_trade_scan_ts`
- `last_snapshot_sync_ts`
- `last_registry_write_ts`
- `active_trade_count`
- `snapshot_failures_last_7d`
- `last_error_message`

## AI Layer

### AI Export Use Cases

1. Single-trade review
2. Weekly trade review
3. Leak detection
4. Setup performance comparison
5. Behavioral pattern detection

### Export Shapes

#### Trade Summary

One row per trade with:

- setup
- underlying
- open/close
- dte
- max profit/loss
- realized pnl
- best pnl seen
- max drawdown
- close reason

#### Snapshot History

One row per timestamp per trade with:

- snapshot_ts
- trade_id
- pnl
- delta
- underlying_price
- vix
- regime_tag

#### Review Dataset

One row per closed trade with:

- leak_tag
- strength_tag
- rule adherence
- comments
- AI review prompt

## Migration Strategy

### Phase 1

Keep the current workbook live.
Build the new workbook in parallel.

### Phase 2

Move Make write operations to:

- `db_import_queue`
- `db_trade_registry`
- `db_snapshots`

### Phase 3

Replace old monthly visual blocks with:

- `Trade Monitor`
- `Active Trades`
- `Closed Trades`
- `Performance`

### Phase 4

Create two distribution versions:

1. `Desk Master`
   Full file for Joao.

2. `Cristiano View`
   Shared copy with only executive and review tabs visible.

## What This Solves

- no more brittle horizontal block scaling,
- easier automation,
- cleaner sharing,
- faster dashboard creation,
- direct AI export path,
- lower maintenance cost,
- better auditability.

## Recommended Next Build Steps

1. Finalize the target schema.
2. Build the styled workbook template.
3. Map current columns to the new registry.
4. Add Make integration rules.
5. Create a Cristiano-specific shared view.
