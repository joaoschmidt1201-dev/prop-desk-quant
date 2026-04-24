Prop Desk Quant — Data Map        

  ---                                                                                                        Storage Locations
                                                                                                           
  ┌────────────────────────────┬─────────────────────────────────────┬────────────────────────────────┐
  │          Location          │                Type                 │          Persisted In          │
  ├────────────────────────────┼─────────────────────────────────────┼────────────────────────────────┤    
  │ G:/Meu                     │ Options chain parquets              │ Google Drive (local mount)     │    
  │ Drive/Quant_Data_MD/       │                                     │                                │    
  ├────────────────────────────┼─────────────────────────────────────┼────────────────────────────────┤    
  │ data/                      │ Spot caches, GEX CSVs, MenthorQ     │ Local disk only — gitignored   │    
  │                            │ levels                              │                                │    
  ├────────────────────────────┼─────────────────────────────────────┼────────────────────────────────┤    
  │ reports/ic7_backtest/      │ Backtest outputs                    │ Git (CSVs only) + local        │    
  │                            │                                     │ (charts)                       │    
  ├────────────────────────────┼─────────────────────────────────────┼────────────────────────────────┤    
  │ reports/ss42_backtest/     │ SS42 outputs                        │ Local only — gitignored        │    
  ├────────────────────────────┼─────────────────────────────────────┼────────────────────────────────┤    
  │ tradingview/               │ Pine Script indicator               │ Git                            │    
  ├────────────────────────────┼─────────────────────────────────────┼────────────────────────────────┤    
  │ gex_history*.json          │ GEX level history                   │ Git                            │    
  ├────────────────────────────┼─────────────────────────────────────┼────────────────────────────────┤    
  │ .env                       │ API keys and secrets                │ Local only — gitignored        │    
  ├────────────────────────────┼─────────────────────────────────────┼────────────────────────────────┤    
  │ .github/workflows/         │ CI/CD automation                    │ Git                            │    
  └────────────────────────────┴─────────────────────────────────────┴────────────────────────────────┘    

  ---
  Parquet Store — G:/Meu Drive/Quant_Data_MD/

  This is the central data lake. All backtest engines read from here.

  {UNDERLYING}_chain_YYYY-MM-DD.parquet

  One file per trading day per underlying. Three series currently exist:

  ┌─────────────────────┬─────────────────────┬────────────┐
  │       Series        │      Coverage       │   Count    │
  ├─────────────────────┼─────────────────────┼────────────┤
  │ NDX_chain_*.parquet │ Apr 2025 – Apr 2026 │ ~246 files │
  ├─────────────────────┼─────────────────────┼────────────┤
  │ SPX_chain_*.parquet │ Apr 2025 – Apr 2026 │ ~250 files │
  ├─────────────────────┼─────────────────────┼────────────┤
  │ RUT_chain_*.parquet │ Apr 2025 – Apr 2026 │ ~250 files │
  └─────────────────────┴─────────────────────┴────────────┘

  Schema:

  ┌──────────────────┬────────────────────┬─────────────────────────────────────────────────┐
  │      Column      │        Type        │                   Description                   │
  ├──────────────────┼────────────────────┼─────────────────────────────────────────────────┤
  │ side             │ category           │ call or put                                     │
  ├──────────────────┼────────────────────┼─────────────────────────────────────────────────┤
  │ strike           │ int64 / float64    │ Strike price in index points                    │
  ├──────────────────┼────────────────────┼─────────────────────────────────────────────────┤
  │ dte              │ int64              │ Calendar days to expiration (used by backtests) │
  ├──────────────────┼────────────────────┼─────────────────────────────────────────────────┤
  │ dte_actual       │ int16              │ Same as dte — legacy column from extractor      │
  ├──────────────────┼────────────────────┼─────────────────────────────────────────────────┤
  │ bid              │ float32            │ Bid price                                       │
  ├──────────────────┼────────────────────┼─────────────────────────────────────────────────┤
  │ mid              │ float32            │ Mid price (bid+ask)/2 — primary pricing column  │
  ├──────────────────┼────────────────────┼─────────────────────────────────────────────────┤
  │ ask              │ float32            │ Ask price                                       │
  ├──────────────────┼────────────────────┼─────────────────────────────────────────────────┤
  │ open_interest    │ int32              │ Open interest                                   │
  ├──────────────────┼────────────────────┼─────────────────────────────────────────────────┤
  │ underlying_price │ float32            │ Spot price at time of snapshot                  │
  ├──────────────────┼────────────────────┼─────────────────────────────────────────────────┤
  │ trade_date       │ datetime64[ns,UTC] │ The trading day this snapshot was captured      │
  ├──────────────────┼────────────────────┼─────────────────────────────────────────────────┤
  │ expiration       │ datetime64[ns,UTC] │ Option expiration date                          │
  ├──────────────────┼────────────────────┼─────────────────────────────────────────────────┤
  │ volume           │ int32              │ Daily volume                                    │
  └──────────────────┴────────────────────┴─────────────────────────────────────────────────┘

  Written by: md_step2_mass_extractor.py, md_step3_strangle_extractor.py, ibkr_step3_daily_assembler.py    

  Read by: ic7_backtest.py, ss42_backtest.py, ic7_viewer.py (optional re-entry simulation)

  Critical: Yes — no parquets means no backtest, no trade proposals.

  ---
  Spot Price Caches — data/

  data/ndx_closes_cache.csv

  ┌────────┬──────────────────────────┐
  │ Column │         Content          │
  ├────────┼──────────────────────────┤
  │ date   │ Trading day (YYYY-MM-DD) │
  ├────────┼──────────────────────────┤
  │ Close  │ NDX closing price        │
  └────────┴──────────────────────────┘

  Written by: md_step2_mass_extractor.py (initially via yfinance), manually appended when yfinance is      
  rate-limited (spot derived from put-call parity)

  Read by: md_step2_mass_extractor.py — determines which trading days to process AND provides spot for ATM 
  strike filter

  Critical: Yes for running the extractor. If a date is missing from this cache, that trading day is       
  skipped entirely.

  ▎ No equivalent cache files for SPX or RUT currently exist. md_step3_strangle_extractor.py uses yfinance 
  ▎ directly instead of a local cache.

  ---
  GEX Data — data/ and root

  data/$SPX-gamma-levels-exp-YYYYMMDD-weekly.csv

  data/$IUXX-gamma-levels-exp-YYYYMMDD-weekly.csv

  data/SPY-gamma-levels-exp-YYYYMMDD-weekly.csv

  data/QQQ-gamma-levels-exp-YYYYMMDD-weekly.csv

  Raw GEX exports downloaded manually from Barchart. One file per ticker per week.

  Written by: Manual download (browser)

  Read by: gex_csv_parser.py — parsed once per week, then discarded (not committed)

  Critical: Input to the GEX workflow. Ephemeral — not stored permanently after processing.

  data/menthorq_levels.csv

  Progressive append log of MenthorQ GEX snapshots.

  Schema: date, timestamp, run_id, call_res, call_res_0dte, put_sup, put_sup_0dte, hvl, hvl_0dte, net_gex, 
  gamma_condition

  Written by: mq_scraper.py

  Read by: gex_compare.py (validation against Barchart levels)

  Critical: No — validation use only.

  ---
  GEX History — Git Root

  gex_history.json — SPX levels

  gex_history_ndx.json — NDX levels

  gex_history_spy.json — SPY levels

  gex_history_qqq.json — QQQ levels

  Structured JSON array. Each entry is one week's computed GEX levels for that ticker (Gamma Flip, Put/Call
   walls p1–p3/n1–n3, COI, POI, zones, confluences, spot at time of computation).

  Written by: gex_csv_parser.py (appends on every weekly run)

  Read by: morning_briefing.py (reads latest entry for briefing content)

  Critical: Yes for morning briefing. If stale (not updated Monday), briefing uses last week's levels.     

  In git: Yes — committed every Monday so GitHub Actions can read them.

  ---
  Backtest Outputs — reports/ic7_backtest/

  IC7_7DTE_NDX_{start}_{end}.csv ← Critical

  The main trade log. One row per executed trade.

  Key columns: trade_date, exp_date, spot_entry, iv_atm, expected_move, short_put, long_put, short_call,   
  long_call, total_credit, spot_exit, pnl_points, pnl_usd, result

  Written by: ic7_backtest.py

  Read by: ic7_viewer.py (Performance tab — equity curve, drawdown, heatmap, distribution)

  In git: Yes — this file is what Streamlit Cloud deploys from.

  IC7_7DTE_NDX_daily_{start}_{end}.csv ← Critical

  Daily mark-to-market for every trade. One row per calendar day per trade.

  Key columns: trade_date, calendar_date, dte_remaining, spot, pnl_usd, source

  source values: market (real mid prices), bs_model (Black-Scholes fallback), intrinsic (expiration day)   

  Written by: ic7_backtest.py

  Read by: ic7_viewer.py (Trade Inspector tab — Close Rules engine, P&L timeline chart)

  In git: Yes — required for Close Rules to work in the viewer.

  performance_report.txt

  Human-readable summary: win rate, Sharpe, Sortino, max drawdown, profit factor, avg credit.

  Written by: ic7_backtest.py

  Read by: No script — reference only.

  In git: No — gitignored.

  equity_curve.png, drawdown.png, pnl_distribution.png, monthly_heatmap.png

  Static charts generated by the backtest.

  Written by: ic7_backtest.py

  In git: No — gitignored. Streamlit viewer generates its own interactive versions from the CSV.

  ---
  SS42 Outputs — reports/ss42_backtest/

  SS42_{UNDERLYING}_{start}_{end}.csv

  Trade log for the Short Strangle 42DTE strategy.

  Written by: ss42_backtest.py

  Read by: ss42_reinvest_sim.py (optional compounding simulation)

  In git: No — currently gitignored / untracked.

  ---
  TradingView — tradingview/

  tradingview/gex_weekly_levels.pine

  Pine Script indicator for TradingView. Auto-switches GEX levels by ticker. Displays horizontal lines at  
  all GEX structural levels for the current week.

  Written by: gex_csv_parser.py (regenerated in full every Monday run)

  Read by: TradingView (manual import by analyst — copy-paste into indicator editor)

  In git: Yes.

  ---
  IBKR Pipeline Intermediates — data/

  data/ibkr_contract_universe.parquet

  Full grid of (underlying × expiration × strike × side) for the backfill period. Generated once, reused by
   the downloader.

  Written by: ibkr_step1_contract_gen.py

  Read by: ibkr_step2_bulk_downloader.py

  data/{UNDERLYING}_spot_cache.csv

  Spot price cache per underlying, used during contract universe generation.

  Written by: ibkr_step1_contract_gen.py (via yfinance)

  Read by: ibkr_step1_contract_gen.py (cache check on next run)

  ---
  Configuration & Secrets — Root

  .env

  THETADATA_API_KEY=          # empty — subscription not active
  DISCORD_WEBHOOK_URL=...
  PERPLEXITY_API_KEY=...
  FINNHUB_API_KEY=...

  Read by: morning_briefing.py, dry_run_briefing.py, thetadata_step1_download.py

  In git: No — gitignored. GitHub Actions uses its own Secrets store (separate from .env).

  .github/workflows/morning_briefing.yml

  Defines the cron schedule, runner environment, and script invocation for automated briefing.

  In git: Yes.

  ---
  Read/Write Summary

  ┌────────────────────────────────────────┬───────────────────────┬────────────────────────────┬──────┐   
  │             File / Dataset             │      Written by       │          Read by           │ In   │   
  │                                        │                       │                            │ Git  │   
  ├────────────────────────────────────────┼───────────────────────┼────────────────────────────┼──────┤   
  │ NDX/SPX/RUT_chain_*.parquet            │ md_step2, md_step3,   │ ic7_backtest,              │ No   │   
  │                                        │ ibkr_step3            │ ss42_backtest, ic7_viewer  │      │   
  ├────────────────────────────────────────┼───────────────────────┼────────────────────────────┼──────┤   
  │ data/ndx_closes_cache.csv              │ md_step2 + manual     │ md_step2                   │ No   │   
  ├────────────────────────────────────────┼───────────────────────┼────────────────────────────┼──────┤   
  │ data/$SPX/$IUXX/SPY/QQQ-gamma-*.csv    │ Manual download       │ gex_csv_parser             │ No   │   
  ├────────────────────────────────────────┼───────────────────────┼────────────────────────────┼──────┤   
  │ gex_history*.json                      │ gex_csv_parser        │ morning_briefing           │ Yes  │   
  ├────────────────────────────────────────┼───────────────────────┼────────────────────────────┼──────┤   
  │ data/menthorq_levels.csv               │ mq_scraper            │ gex_compare                │ No   │   
  ├────────────────────────────────────────┼───────────────────────┼────────────────────────────┼──────┤   
  │ IC7_7DTE_NDX_*.csv (trade log)         │ ic7_backtest          │ ic7_viewer                 │ Yes  │   
  ├────────────────────────────────────────┼───────────────────────┼────────────────────────────┼──────┤   
  │ IC7_7DTE_NDX_daily_*.csv               │ ic7_backtest          │ ic7_viewer                 │ Yes  │   
  ├────────────────────────────────────────┼───────────────────────┼────────────────────────────┼──────┤   
  │ SS42_{UNDERLYING}_*.csv                │ ss42_backtest         │ ss42_reinvest_sim          │ No   │   
  ├────────────────────────────────────────┼───────────────────────┼────────────────────────────┼──────┤   
  │ tradingview/gex_weekly_levels.pine     │ gex_csv_parser        │ TradingView (manual)       │ Yes  │   
  ├────────────────────────────────────────┼───────────────────────┼────────────────────────────┼──────┤   
  │ data/ibkr_contract_universe.parquet    │ ibkr_step1            │ ibkr_step2                 │ No   │   
  ├────────────────────────────────────────┼───────────────────────┼────────────────────────────┼──────┤   
  │ .env                                   │ Manual                │ morning_briefing,          │ No   │   
  │                                        │                       │ dry_run_briefing           │      │   
  ├────────────────────────────────────────┼───────────────────────┼────────────────────────────┼──────┤   
  │ .github/workflows/morning_briefing.yml │ Manual                │ GitHub Actions             │ Yes  │   
  └────────────────────────────────────────┴───────────────────────┴────────────────────────────┴──────┘   

  ---
  What Must Be Present for Each Workflow

  ┌─────────────────────────┬────────────────────────────────────────────────────────────────┐
  │        Workflow         │                         Required Files                         │
  ├─────────────────────────┼────────────────────────────────────────────────────────────────┤
  │ Morning Briefing (auto) │ gex_history*.json (committed), GitHub Secrets set              │
  ├─────────────────────────┼────────────────────────────────────────────────────────────────┤
  │ GEX Update              │ Barchart CSV in data/                                          │
  ├─────────────────────────┼────────────────────────────────────────────────────────────────┤
  │ IC7 Backtest            │ NDX_chain_*.parquet in Google Drive                            │
  ├─────────────────────────┼────────────────────────────────────────────────────────────────┤
  │ IC7 Viewer (Streamlit)  │ IC7_7DTE_NDX_*.csv + IC7_7DTE_NDX_daily_*.csv committed to git │
  ├─────────────────────────┼────────────────────────────────────────────────────────────────┤
  │ SS42 Backtest           │ SPX_chain_*.parquet or RUT_chain_*.parquet in Google Drive     │
  ├─────────────────────────┼────────────────────────────────────────────────────────────────┤
  │ IBKR Backfill           │ TWS running locally + data/ibkr_contract_universe.parquet      │
  ├─────────────────────────┼────────────────────────────────────────────────────────────────┤
  │ Chain Data Update (NDX) │ data/ndx_closes_cache.csv with dates to process                │
  └─────────────────────────┴────────────────────────────────────────────────────────────────