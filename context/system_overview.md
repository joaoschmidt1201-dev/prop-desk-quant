Prop Desk Quant — System Overview                                                                        
                                                                                                           
  What This System Does                                                                                    
                                                                                                             A quantitative options trading desk infrastructure that removes human emotion from options trading 
  decisions. The system backtests, validates, and delivers Iron Condor and Short Strangle strategies on    
  macro index underlyings (NDX, SPX, RUT) using real market data. It feeds processed signals to the Head
  Trader (Cristiano) for final execution.

  Core philosophy: Merge TastyTrade options methodology (volatility selling, IV rank, probability of       
  profit) with technical analysis (GEX levels, moving averages, support/resistance). Math must agree with  
  chart structure before any trade is proposed.

  ---
  Asset Universe & Constraints

  - Underlyings: NDX, SPX, RUT (index options only — European exercise, cash-settled)
  - Minimum DTE: 7 days — no intraday, no 0DTE
  - No individual stocks — zero idiosyncratic risk
  - No live order execution — the system is a decision engine only; Cristiano executes manually

  ---
  Main Components

  1. IC7 Strategy — Iron Condor 7DTE (Primary)

  The flagship strategy. Entry every Friday, exit the following Friday at expiration.

  ┌─────────────────┬───────────────────────────────────────────────────────────────────────────────────┐  
  │     Script      │                                       Role                                        │  
  ├─────────────────┼───────────────────────────────────────────────────────────────────────────────────┤  
  │ ic7_backtest.py │ Full historical backtest engine — selects optimal strikes, computes P&L, daily    │  
  │                 │ MTM, performance report                                                           │  
  ├─────────────────┼───────────────────────────────────────────────────────────────────────────────────┤  
  │ ic7_viewer.py   │ Streamlit dashboard — Trade Inspector (payoff chart, strikes, close rules) +      │  
  │                 │ Performance tab (equity curve, drawdown, heatmap)                                 │  
  └─────────────────┴───────────────────────────────────────────────────────────────────────────────────┘  

  Structure: Short Put Spread (50pt width) + Short Call Spread (100pt width) on NDX. Strikes placed just   
  beyond ±1 standard deviation using EM = Spot × IV_ATM × √(DTE/365).

  Close Rules tracked: 50% profit target, 4 DTE exit, 1× max profit stop.

  ---
  2. SS42 Strategy — Short Strangle 42DTE

  Secondary strategy on SPX and RUT.

  ┌──────────────────────┬──────────────────────────────────────────────────────────────────────────────┐  
  │        Script        │                                     Role                                     │  
  ├──────────────────────┼──────────────────────────────────────────────────────────────────────────────┤  
  │                      │ Backtests short strangle entered at ~42 DTE on the first Friday of the       │  
  │ ss42_backtest.py     │ month, exits at expiration. Strikes at ~16-delta (computed via               │  
  │                      │ Black-Scholes). Checkpoint at ~21 DTE (TastyTrade standard).                 │  
  ├──────────────────────┼──────────────────────────────────────────────────────────────────────────────┤  
  │ ss42_reinvest_sim.py │ Simulates reinvestment/compounding on SS42 results                           │  
  └──────────────────────┴──────────────────────────────────────────────────────────────────────────────┘  

  ---
  3. Market Data Pipeline — Primary Data Source

  Uses the Market Data App API (api.marketdata.app/v1, plan: 100k req/day).

  ┌────────────────────────────────┬────────────────────────────────────────────────────────────────────┐  
  │             Script             │                                Role                                │  
  ├────────────────────────────────┼────────────────────────────────────────────────────────────────────┤  
  │ md_step1_extractor.py          │ Unit-test extractor — validates a single date/expiration before    │  
  │                                │ scaling                                                            │  
  ├────────────────────────────────┼────────────────────────────────────────────────────────────────────┤  
  │                                │ Main pipeline. Bulk historical download: for each trading day,     │  
  │ md_step2_mass_extractor.py     │ fetches all expirations 0–45 DTE, applies ATM ±30 strike radius    │  
  │                                │ filter, saves {UNDERLYING}_chain_YYYY-MM-DD.parquet. Idempotent    │  
  │                                │ (skips existing files).                                            │  
  ├────────────────────────────────┼────────────────────────────────────────────────────────────────────┤  
  │ md_step3_strangle_extractor.py │ Variant for SS42 data: wider strike radius (±100 positions),       │  
  │                                │ MAX_DTE=55 to capture 42DTE strikes at 16-delta                    │  
  └────────────────────────────────┴────────────────────────────────────────────────────────────────────┘  

  Output: G:/Meu Drive/Quant_Data_MD/{UNDERLYING}_chain_YYYY-MM-DD.parquet
  Coverage: NDX Apr 2025–Apr 2026 (~244 files), SPX/RUT Apr 2025–Apr 2026

  Parquet schema: side, strike, dte, dte_actual, bid, mid, ask, open_interest, underlying_price,
  trade_date, expiration, volume

  ---
  4. IBKR Backfill Pipeline

  For fetching historical options data from Interactive Brokers TWS API (fills gaps not covered by Market  
  Data App).

  ┌───────────────────────────────┬─────────────────────────────────────────────────────────────────────┐  
  │            Script             │                                Role                                 │  
  ├───────────────────────────────┼─────────────────────────────────────────────────────────────────────┤  
  │                               │ Generates contract universe (expiration × strike × side) for a date │  
  │ ibkr_step1_contract_gen.py    │  range. Uses yfinance for spot prices; generates all CBOE-compliant │  
  │                               │  expirations (SPXW weeklies Mon/Wed/Fri + SPX monthly AM). Saves    │  
  │                               │ data/ibkr_contract_universe.parquet                                 │  
  ├───────────────────────────────┼─────────────────────────────────────────────────────────────────────┤  
  │ ibkr_step2_bulk_downloader.py │ Connects to TWS API and downloads historical options data for each  │  
  │                               │ contract in the universe. Rate-limited, checkpointed.               │  
  ├───────────────────────────────┼─────────────────────────────────────────────────────────────────────┤  
  │ ibkr_step3_daily_assembler.py │ Assembles IBKR raw downloads into per-day parquets in the same      │  
  │                               │ schema as the Market Data pipeline                                  │  
  └───────────────────────────────┴─────────────────────────────────────────────────────────────────────┘  

  ---
  5. ThetaData Pipeline (planned, not yet active)

  Scripts exist but the API subscription was never activated (THETADATA_API_KEY is empty in .env).

  ┌─────────────────────────────┬───────────────────────────────────────────────────────────────────────┐  
  │           Script            │                                 Role                                  │  
  ├─────────────────────────────┼───────────────────────────────────────────────────────────────────────┤  
  │ thetadata_step1_download.py │ Would bulk-download EOD options chain by expiration from ThetaData    │  
  │                             │ Standard API. Targets SPX (via SPXW), RUT, NDX; 8 years of history.   │  
  ├─────────────────────────────┼───────────────────────────────────────────────────────────────────────┤  
  │ thetadata_step2_assemble.py │ Would assemble ThetaData raw parquets into the standard daily format  │  
  └─────────────────────────────┴───────────────────────────────────────────────────────────────────────┘  

  ---
  6. GEX Pipeline — Gamma Exposure Levels

  Tracks institutional gamma exposure to identify key price levels weekly.

  ┌───────────────────┬─────────────────────────────────────────────────────────────────────────────────┐  
  │      Script       │                                      Role                                       │  
  ├───────────────────┼─────────────────────────────────────────────────────────────────────────────────┤  
  │                   │ Core tool. Reads Barchart GEX CSV (SPX, NDX, SPY, QQQ), computes all GEX levels │  
  │ gex_csv_parser.py │  (Gamma Flip, put/call walls p1–p3/n1–n3, COI, POI, aggregate zones,            │  
  │                   │ confluences), saves to per-ticker JSON history, regenerates the TradingView     │  
  │                   │ Pine Script indicator                                                           │  
  ├───────────────────┼─────────────────────────────────────────────────────────────────────────────────┤  
  │ gex_input.py      │ UI helper for inputting GEX data                                                │  
  ├───────────────────┼─────────────────────────────────────────────────────────────────────────────────┤  
  │ gex_compare.py    │ Compares GEX levels across sources (Barchart vs TradingLit vs MenthorQ) for     │  
  │                   │ tri-source validation                                                           │  
  ├───────────────────┼─────────────────────────────────────────────────────────────────────────────────┤  
  │ gex_ocr_helper.py │ OCR helper for extracting GEX levels from screenshots                           │  
  ├───────────────────┼─────────────────────────────────────────────────────────────────────────────────┤  
  │                   │ MenthorQ historical levels scraper — browser automation (Playwright) with       │  
  │ mq_scraper.py     │ manual login, then programmatic snapshot scraping. Extracts 6 price levels +    │  
  │                   │ Net GEX + Gamma Condition per snapshot, saves to data/menthorq_levels.csv       │  
  └───────────────────┴─────────────────────────────────────────────────────────────────────────────────┘  

  GEX history files: gex_history.json, gex_history_ndx.json, gex_history_spy.json, gex_history_qqq.json    
  Pine Script output: tradingview/gex_weekly_levels.pine (single indicator, auto-switches ticker based on  
  chart)

  ---
  7. Morning Briefing — Automated Daily Report

  Generates and posts a pre-market briefing to Discord every weekday.

  ┌─────────────────────┬───────────────────────────────────────────────────────────────────────────────┐  
  │       Script        │                                     Role                                      │  
  ├─────────────────────┼───────────────────────────────────────────────────────────────────────────────┤  
  │                     │ Pulls VIX, ES/NQ/RTY futures, SPX price + MAs from yfinance; loads GEX levels │  
  │ morning_briefing.py │  from committed JSON; calls Perplexity API for real-time news research;       │  
  │                     │ formats full briefing; POSTs to Discord webhook                               │  
  ├─────────────────────┼───────────────────────────────────────────────────────────────────────────────┤  
  │ dry_run_briefing.py │ Same logic but prints to terminal instead of posting — for local testing      │  
  └─────────────────────┴───────────────────────────────────────────────────────────────────────────────┘  

  Automation: GitHub Actions (.github/workflows/morning_briefing.yml) — scheduled 11:00 UTC (08:00 BRT),   
  weekdays only, triggers morning_briefing.py in the cloud.

  Secrets required: PERPLEXITY_API_KEY, DISCORD_WEBHOOK_URL, FINNHUB_API_KEY (for earnings intelligence —  
  anti-hallucination EPS actuals).

  ---
  8. Legacy Databento Pipeline (archived)

  Original data source, replaced by Market Data App.

  Located in scripts/legacy_databento/:
  db_step1_definition.py → db_step2_filter_ids.py → db_step3_cbbo_targeted.py
  Supporting: ic7_simulator.py (original simulator), db_batch_extractor.py, db_merge_definitions.py,       
  db_kill_job.py

  ---
  9. Utilities

  ┌────────────────────────┬───────────────────────────────────────────────────────────────────────────┐   
  │         Script         │                                   Role                                    │   
  ├────────────────────────┼───────────────────────────────────────────────────────────────────────────┤   
  │ whisper_transcriber.py │ Local Whisper transcription — for transcribing trading meeting recordings │   
  └────────────────────────┴───────────────────────────────────────────────────────────────────────────┘   

  ---
  Core Data Flow

  RAW DATA SOURCES
    Market Data App API  ──→  md_step2_mass_extractor.py
    IBKR TWS API         ──→  ibkr_step1/2/3
    Barchart CSV (manual)──→  gex_csv_parser.py
    MenthorQ (browser)   ──→  mq_scraper.py
           │
           ▼
  PARQUET STORE  (G:/Meu Drive/Quant_Data_MD/)
    {UNDERLYING}_chain_YYYY-MM-DD.parquet
    (one file per trading day per underlying)
           │
           ▼
  BACKTEST ENGINES
    ic7_backtest.py  ──→  reports/ic7_backtest/
      IC7_7DTE_NDX_{start}_{end}.csv          ← trade log
      IC7_7DTE_NDX_daily_{start}_{end}.csv    ← daily MTM (Close Rules data)
    ss42_backtest.py ──→  reports/ss42_backtest/
           │
           ▼
  STREAMLIT VIEWER  (ic7_viewer.py)
    Deployed on Streamlit Cloud
    Repo: joaoschmidt1201-dev/prop-desk-quant
    Auto-deploys on push to main
    Reads CSVs from reports/ (committed to git)
           │
           ▼
  HEAD TRADER OUTPUT
    Morning Briefing → Discord (GitHub Actions)
    GEX Pine Script  → TradingView (manual import)
    Trade proposals  → Cristiano for final execution

  ---
  Infrastructure

  ┌────────────────┬────────────────────────────────────────────────────────────────────────┐
  │   Component    │                                 Detail                                 │
  ├────────────────┼────────────────────────────────────────────────────────────────────────┤
  │ Runtime        │ Python 3.x, conda env trade_env                                        │
  ├────────────────┼────────────────────────────────────────────────────────────────────────┤
  │ Data store     │ Google Drive (G:/Meu Drive/Quant_Data_MD) via Google Drive for Desktop │
  ├────────────────┼────────────────────────────────────────────────────────────────────────┤
  │ CI/CD          │ GitHub Actions — morning briefing automation                           │
  ├────────────────┼────────────────────────────────────────────────────────────────────────┤
  │ Viewer hosting │ Streamlit Cloud — auto-deploy from GitHub                              │
  ├────────────────┼────────────────────────────────────────────────────────────────────────┤
  │ Secrets        │ .env file (local) + GitHub Actions Secrets (cloud)                     │
  ├────────────────┼────────────────────────────────────────────────────────────────────────┤
  │ OS             │ Windows 11 (bash via Git Bash/conda)                                   │
  └────────────────┴────────────────────────────────────────────────────────────────────────┘

  ---
  Key External Dependencies

  ┌─────────────────────────┬──────────────────────────────────────────────────────────────────────┐       
  │         Service         │                                 Use                                  │       
  ├─────────────────────────┼──────────────────────────────────────────────────────────────────────┤       
  │ Market Data App API     │ Historical options chains (primary data source)                      │       
  ├─────────────────────────┼──────────────────────────────────────────────────────────────────────┤       
  │ Perplexity API          │ Real-time market news for morning briefing                           │       
  ├─────────────────────────┼──────────────────────────────────────────────────────────────────────┤       
  │ Finnhub API             │ Earnings data (EPS actuals, anti-hallucination guard)                │       
  ├─────────────────────────┼──────────────────────────────────────────────────────────────────────┤       
  │ Discord Webhook         │ Morning briefing delivery                                            │       
  ├─────────────────────────┼──────────────────────────────────────────────────────────────────────┤       
  │ yfinance                │ Spot prices for IBKR contract generation and briefing (rate-limited) │       
  ├─────────────────────────┼──────────────────────────────────────────────────────────────────────┤       
  │ Interactive Brokers TWS │ Backfill data source (requires running TWS locally)                  │       
  └─────────────────────────┴──────────────────────────────────────────────────────────────────────┘       