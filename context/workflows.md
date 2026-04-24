Prop Desk Quant — Workflows Document

  ---                                                                                                        Weekly Rhythm Overview
                                                                                                           
  ┌─────────────────────────────────┬─────────────────────────────────────────────┬───────────────────┐
  │             Timing              │                  Workflow                   │     Critical?     │
  ├─────────────────────────────────┼─────────────────────────────────────────────┼───────────────────┤    
  │ Every weekday, 08:00 BRT (auto) │ Morning Briefing → Discord                  │ Yes               │    
  ├─────────────────────────────────┼─────────────────────────────────────────────┼───────────────────┤    
  │ Every Monday                    │ GEX levels update                           │ Yes               │    
  ├─────────────────────────────────┼─────────────────────────────────────────────┼───────────────────┤    
  │ Every Friday                    │ Backtest data update + new trade evaluation │ Yes               │    
  ├─────────────────────────────────┼─────────────────────────────────────────────┼───────────────────┤    
  │ On demand                       │ Backtest re-run after data update           │ When data changes │    
  ├─────────────────────────────────┼─────────────────────────────────────────────┼───────────────────┤    
  │ On demand                       │ MenthorQ scrape                             │ Optional          │    
  └─────────────────────────────────┴─────────────────────────────────────────────┴───────────────────┘    

  ---
  Workflow 1 — Daily Morning Briefing (Automated)

  Trigger: GitHub Actions cron, 11:00 UTC / 08:00 BRT, weekdays only
  No manual action required on normal days.

  Execution sequence:

  GitHub Actions runner (ubuntu-latest)
    └─ python scripts/morning_briefing.py
          1. yfinance  → fetches VIX, ES/NQ/RTY futures, SPX price + 20/50/200 MA
          2. gex_history.json (committed) → loads last GEX levels (no API call)
          3. Perplexity API → researches real-time macro/market news
          4. Finnhub API → fetches earnings calendar (EPS actuals for near-term events)
          5. Formats full briefing text
          6. POST → Discord webhook

  To test locally before pushing changes:
  python scripts/dry_run_briefing.py
  Prints to terminal. Does not post to Discord. Requires PERPLEXITY_API_KEY and FINNHUB_API_KEY in .env.   

  Failure mode: If GitHub Actions delays (up to 2h), briefing arrives by 10:00 BRT at the latest — still   
  before market open (10:30 BRT). Manual trigger available via GitHub Actions UI tab.

  ---
  Workflow 2 — Weekly GEX Update (Every Monday)

  Trigger: Manual. Barchart CSVs downloaded by hand from the website.

  Execution sequence:

  Step 1 — Download CSVs from Barchart (manual, browser)
  - Download 4 files: SPX ($SPX), NDX ($IUXX), SPY, QQQ
  - Save to data/ directory

  Step 2 — Run gex_csv_parser.py for each ticker
  python scripts/gex_csv_parser.py "data/$SPX-gamma-levels-exp-YYYYMMDD-weekly.csv"  --week YYYY-MM-DD     
  python scripts/gex_csv_parser.py "data/$IUXX-gamma-levels-exp-YYYYMMDD-weekly.csv" --week YYYY-MM-DD     
  python scripts/gex_csv_parser.py "data/SPY-gamma-levels-exp-YYYYMMDD-weekly.csv"   --week YYYY-MM-DD     
  python scripts/gex_csv_parser.py "data/QQQ-gamma-levels-exp-YYYYMMDD-weekly.csv"   --week YYYY-MM-DD     

  Each run:
  - Computes all GEX levels (Gamma Flip, Put/Call walls p1–p3/n1–n3, COI, POI, zones, confluences)
  - Appends to the ticker's JSON history file (gex_history.json, etc.)
  - Regenerates tradingview/gex_weekly_levels.pine
  - Prints terminal summary with point distances to spot

  Step 3 — Commit and push
  git add gex_history*.json tradingview/gex_weekly_levels.pine
  git commit -m "chore: GEX levels week YYYY-MM-DD"
  git push

  Effect: Morning briefing now uses updated GEX levels (reads from committed JSON). Pine Script indicator  
  updated for TradingView import.

  Optional — MenthorQ validation:
  python scripts/mq_scraper.py
  Requires non-headless browser + manual login. Scrapes historical MenthorQ snapshots →
  data/menthorq_levels.csv. Then:
  python scripts/gex_compare.py
  Compares Barchart vs TradingLit vs MenthorQ. Used to validate primary source, not required weekly.       

  ---
  Workflow 3 — Options Chain Data Update (Friday / Weekly)

  Keeps the parquet store current so the backtests use real market data.

  Script: md_step2_mass_extractor.py
  Output dir: G:/Meu Drive/Quant_Data_MD/
  Prerequisite: Google Drive mounted at G:/

  Step 1 — Update closes cache

  The script uses data/ndx_closes_cache.csv (and equivalent per-underlying) to know which trading days to  
  process and what the spot price was (for the ATM strike filter). Before running, append any missing dates
   and closes.

  Step 2 — Run extractor per underlying

  Edit UNDERLYING and DATE_END at the top of the script, then:
  python scripts/md_step2_mass_extractor.py

  The script is idempotent — it skips any date where the parquet already exists. Run once per underlying   
  (NDX, SPX, RUT). Each run costs ~8–9 API calls per new trading day.

  For SS42 data (wider strike coverage):
  python scripts/md_step3_strangle_extractor.py
  Same flow but with STRIKE_RADIUS=100 and MAX_DTE=55 — needed for 16-delta strikes at 42 DTE.

  Step 3 — Verify coverage

  ls "G:/Meu Drive/Quant_Data_MD/" | grep "NDX_chain" | tail -5
  ls "G:/Meu Drive/Quant_Data_MD/" | grep "SPX_chain" | tail -5
  ls "G:/Meu Drive/Quant_Data_MD/" | grep "RUT_chain" | tail -5

  No commit needed — parquet store lives on Google Drive, not in git.

  ---
  Workflow 4 — IC7 Backtest Re-run (After Data Update)

  Run whenever new parquets have been added to the store.

  Execution sequence:

  Step 1 — Run backtest
  python scripts/ic7_backtest.py

  Reads all NDX_chain_YYYY-MM-DD.parquet from G:/Meu Drive/Quant_Data_MD/.
  Discovers valid Friday entry/exit pairs automatically.
  Outputs to reports/ic7_backtest/:

  ┌──────────────────────────────────────┬──────────────────────────────────────────────────────────────┐  
  │                 File                 │                           Content                            │  
  ├──────────────────────────────────────┼──────────────────────────────────────────────────────────────┤  
  │ IC7_7DTE_NDX_{start}_{end}.csv       │ Trade log — one row per trade                                │  
  ├──────────────────────────────────────┼──────────────────────────────────────────────────────────────┤  
  │ IC7_7DTE_NDX_daily_{start}_{end}.csv │ Daily MTM — P&L per calendar day per trade (feeds Close      │  
  │                                      │ Rules in viewer)                                             │  
  ├──────────────────────────────────────┼──────────────────────────────────────────────────────────────┤  
  │ performance_report.txt               │ Summary stats                                                │  
  ├──────────────────────────────────────┼──────────────────────────────────────────────────────────────┤  
  │ equity_curve.png, drawdown.png, etc. │ Charts (gitignored)                                          │  
  └──────────────────────────────────────┴──────────────────────────────────────────────────────────────┘  

  Step 2 — Commit and push CSVs
  git add reports/ic7_backtest/*.csv
  git commit -m "feat: IC7 backtest update YYYY-MM-DD"
  git push

  Effect: Streamlit Cloud detects the push and redeploys ic7_viewer.py automatically. Viewer reads the new 
  CSVs from the repo.

  ---
  Workflow 5 — SS42 Backtest Re-run

  Same pattern as IC7, but uses SPX and RUT parquets.

  python scripts/ss42_backtest.py SPX
  python scripts/ss42_backtest.py RUT

  Output: reports/ss42_backtest/SS42_{UNDERLYING}_{start}_{end}.csv

  python scripts/ss42_reinvest_sim.py   # optional: compounding simulation

  Commit the CSV if it will be consumed by a viewer or report.

  ---
  Workflow 6 — IBKR Backfill (On-Demand, When Gaps Exist)

  Used when Market Data App does not cover a specific historical date range. Requires Interactive Brokers  
  TWS running locally on the desktop.

  Execution sequence:

  Step 1 — Generate contract universe
  python scripts/ibkr_step1_contract_gen.py --start YYYY-MM-DD --end YYYY-MM-DD
  Pulls spot prices from yfinance. Generates all valid expirations (SPXW weeklies Mon/Wed/Fri + SPX        
  monthly). Produces data/ibkr_contract_universe.parquet.

  Step 2 — Download from TWS
  python scripts/ibkr_step2_bulk_downloader.py
  TWS must be open and API enabled (port 7497). Rate-limited. Checkpointed — safe to interrupt and resume. 

  Step 3 — Assemble daily parquets
  python scripts/ibkr_step3_daily_assembler.py
  Converts IBKR raw downloads into the same {UNDERLYING}_chain_YYYY-MM-DD.parquet schema used by the       
  backtests.

  ---
  Critical vs Optional

  ┌───────────────────┬────────────────────┬───────────────────────────────────────────────────────────┐   
  │     Workflow      │      Critical      │                            Why                            │   
  ├───────────────────┼────────────────────┼───────────────────────────────────────────────────────────┤   
  │ Morning Briefing  │ Yes                │ Daily desk intelligence — fully automated, just keep      │   
  │                   │                    │ GitHub Actions active                                     │   
  ├───────────────────┼────────────────────┼───────────────────────────────────────────────────────────┤   
  │ GEX Update        │ Yes                │ Briefing and trade context depend on current GEX levels   │   
  ├───────────────────┼────────────────────┼───────────────────────────────────────────────────────────┤   
  │ Chain Data Update │ Yes                │ Backtests and close rules require current parquet data    │   
  ├───────────────────┼────────────────────┼───────────────────────────────────────────────────────────┤   
  │ IC7 Backtest      │ Yes (after data    │ Viewer and Close Rules only reflect reality if CSVs are   │   
  │ Re-run            │ update)            │ current                                                   │   
  ├───────────────────┼────────────────────┼───────────────────────────────────────────────────────────┤   
  │ SS42 Backtest     │ Moderate           │ Secondary strategy — run when evaluating SS42 trades      │   
  │ Re-run            │                    │                                                           │   
  ├───────────────────┼────────────────────┼───────────────────────────────────────────────────────────┤   
  │ IBKR Backfill     │ Optional           │ Only needed for historical gaps; Market Data App covers   │   
  │                   │                    │ normal operation                                          │   
  ├───────────────────┼────────────────────┼───────────────────────────────────────────────────────────┤   
  │ MenthorQ Scrape   │ Optional           │ Validation only; Barchart is the primary GEX source       │   
  ├───────────────────┼────────────────────┼───────────────────────────────────────────────────────────┤   
  │ ThetaData         │ Not active         │ Scripts exist but API key is empty — subscription never   │   
  │ Pipeline          │                    │ purchased                                                 │   
  └───────────────────┴────────────────────┴───────────────────────────────────────────────────────────┘   

  ---
  Normal Friday Sequence (Full Operational Week-End)

  This is the combined sequence for a typical Friday:

  1. [AUTO 08:00 BRT]  Morning briefing posted to Discord

  2. [~09:00 BRT]      Run md_step2_mass_extractor.py for NDX (and SPX/RUT if needed)
                       → new parquets added to G:/Meu Drive/Quant_Data_MD/

  3. [After step 2]    python scripts/ic7_backtest.py
                       → new trade log + daily MTM CSVs generated

  4. [After step 3]    git add reports/ic7_backtest/*.csv && git push
                       → Streamlit Cloud redeploys ic7_viewer.py

  5. [Cristiano]       Reviews ic7_viewer.py dashboard
                       → Makes go/no-go decision on next week's Iron Condor entry