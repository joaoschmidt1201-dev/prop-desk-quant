# Dashboard + AI Pack

This pack is designed to sit on top of the existing `OP Control Panel.xlsx` without replacing the current operating logic.

## Added Sheets

- `Dashboard`
  Executive shareable tab for Cristiano.

- `AI Export`
  A single-trade AI export surface with prompt-ready context and latest snapshots.

- `AI Workflow`
  Suggested reporting workflows and prompts.

- `db_dashboard_helper` (hidden)
  Normalized helper table built from the existing tabs:
  - `MAR26`
  - `APR26`
  - `JS-FOR MAR26`
  - `JS APR26`
  - `FOR Trades`

## What The Dashboard Tries To Solve

Without changing the current workbook structure, it adds:

- active trade count,
- open PnL and net delta overview,
- next expiry visibility,
- snapshot freshness,
- priority feed,
- active trade strip,
- quick charts for shareable monitoring.

## What The AI Export Tries To Solve

It gives you one place to:

- pick a live trade URL,
- auto-pull the current context,
- generate a consistent review prompt,
- attach latest snapshots,
- paste the AI report back into the sheet.

## Intended Workflow

1. Keep your existing sheet and Make scenarios.
2. Upload the generated workbook copy to Google Sheets.
3. Check that Google Sheets recalculates the helper formulas.
4. Refine the dashboard styling and metrics based on what Cristiano cares about most.
5. Use the `AI Export` tab for daily/weekly structured reviews.

## Important Constraint

Because the current workbook is highly custom and the source file here is an `.xlsx` export of a Google Sheet, some Google Sheets formulas are only truly testable once uploaded back into Google Sheets.

So this pack should be treated as:

- a concrete additive prototype,
- not the final production version yet.

The next iteration should be done after verifying it inside Google Sheets.
