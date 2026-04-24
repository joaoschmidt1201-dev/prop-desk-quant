Prop Desk Quant — Known Issues

  ---                                                                                                        1. Hard Dependencies on Local Windows Environment
                                                                                                           
  Google Drive mount at G:/

  Every backtest script and extractor hardcodes G:/Meu Drive/Quant_Data_MD/ as the parquet store path. This
   path is:
  - Windows-only
  - Requires Google Drive for Desktop running and signed in
  - Will silently fail on Linux (GitHub Actions, Docker, Codex sandbox) — scripts either crash or skip all 
  files

  Scripts affected: ic7_backtest.py, ss42_backtest.py, md_step2_mass_extractor.py,
  md_step3_strangle_extractor.py, ibkr_step3_daily_assembler.py, ic7_viewer.py

  Migration risk: Critical. Any new environment must either mount Google Drive at the same path or update  
  the path constant in every script. There is no environment variable or config file centralizing this     
  path.

  ---
  Conda environment trade_env

  All scripts assume the conda environment trade_env is active. No requirements.txt or pyproject.toml      
  exists in the repository. The exact package versions are undocumented.

  Known packages required: pandas, numpy, pyarrow, requests, yfinance, scipy, matplotlib, plotly,
  streamlit, python-dotenv, fastparquet, playwright (for mq_scraper)

  Migration risk: High. A new environment must reconstruct dependencies from inference, not from a
  lockfile. Version mismatches in pyarrow specifically can cause parquet read failures (there is already a 
  histogram validation workaround in load_chain for this exact issue).

  ---
  2. Spot Price Caches — Fragile Manual Maintenance

  data/ndx_closes_cache.csv is not auto-maintained

  The NDX closes cache is the sole input that tells md_step2_mass_extractor.py which trading days to       
  process. It must be kept current manually. If it is stale:
  - No new parquets are downloaded for missing dates (silently skipped, no error)
  - The backtest's data coverage appears complete but is actually outdated

  When yfinance is rate-limited (common), the cache must be updated by deriving spot prices from put-call  
  parity via the Market Data App API — a manual, multi-step process.

  No closes cache exists for SPX or RUT

  md_step2_mass_extractor.py hardcodes CLOSES_CACHE to the NDX file regardless of the UNDERLYING variable. 
  When the script was previously run for SPX/RUT, either:
  - A temporary cache existed and was deleted, or
  - The spot was pulled differently

  This is undocumented. Running the script today with UNDERLYING = "SPX" would use NDX spot prices as the  
  ATM filter for SPX options — silently producing parquets with the wrong strike coverage.

  ---
  3. md_step2_mass_extractor.py — Configuration by Hand-Edit

  The script has no CLI arguments. To change underlying, date range, or strike radius, the analyst must    
  hand-edit constants at the top of the file:

  UNDERLYING  = "SPX"      # change this
  DATE_START  = "2025-04-05"
  DATE_END    = "2026-04-01"
  STRIKE_RADIUS = 30

  There is no guard against accidentally running with wrong settings. A misrun with FORCE_OVERWRITE = True 
  (present in md_step3_strangle_extractor.py) would silently overwrite correct parquets.

  ---
  4. ±30 Strike Radius Causes Systematic BS Fallback

  The parquets cover only ±30 strike positions from the ATM on the day of extraction. Iron Condor legs are 
  placed at approximately ±1 standard deviation from spot at entry. As spot moves during the week:
  - OTM put and call wings drift outside the ±30 radius in subsequent daily parquets
  - _get_leg_mid fails to find those strikes
  - Daily MTM falls back to Black-Scholes using entry-day IV — not current IV

  Practical consequence: Close Rules in the viewer (50% profit target, stop loss) fire based on
  BS-approximated P&L on most intermediate days (DTE 1–3). The final trade P&L at expiration is always     
  exact (intrinsic value). The trade log is accurate; the daily MTM is partially approximated.

  Current coverage: ~32% real market data for non-expiration rows, ~68% BS fallback.

  This is a known structural limitation of the ±30 radius choice, not a bug.

  ---
  5. dte_actual Column Has a Known Parsing Bug

  Existing NDX parquets have a dte_actual column that shows -20210 for all rows (overflow/parsing artifact 
  from an earlier extractor version). The backtest correctly uses the dte column instead, which is
  accurate.

  Risk: Any new script that reads dte_actual expecting a valid DTE value will get garbage data. The column 
  exists in the schema but is unreliable in parquets generated before the bug was identified.

  ---
  6. yfinance Rate Limiting — Recurring Breakage

  yfinance (^NDX, ^GSPC, ^RUT) rate-limits frequently with YFRateLimitError. This affects:
  - ibkr_step1_contract_gen.py — cannot generate contract universe without spot prices
  - morning_briefing.py — VIX and futures data may fail during briefing generation
  - Any ad-hoc spot price fetch

  There is no retry logic or fallback source in most scripts. When rate-limited, the script either exits   
  with an error or returns empty data silently.

  Morning briefing risk: If yfinance fails during GitHub Actions execution, the briefing may post with     
  missing or stale market data without any alert to the analyst.

  ---
  7. ThetaData Pipeline — Non-Functional

  thetadata_step1_download.py and thetadata_step2_assemble.py are present and appear complete, but:        
  - THETADATA_API_KEY in .env is empty
  - The domain api.thetadata.us does not resolve on this machine
  - The subscription was never purchased

  These scripts will fail immediately with a DNS error or auth error. They should not be mistaken for a    
  working data source during migration.

  ---
  8. IBKR Pipeline — Requires TWS Running Locally

  ibkr_step2_bulk_downloader.py connects to Interactive Brokers TWS via its local API (port 7497 by        
  default). It cannot run:
  - Without TWS open and logged in
  - Without paper or live account API permissions enabled in TWS settings
  - On any remote machine (GitHub Actions, Docker, cloud VM)

  The pipeline is designed as a desktop-only, on-demand backfill tool.

  ---
  9. MenthorQ Scraper — Requires Manual Browser Session

  mq_scraper.py uses Playwright in non-headless mode. The workflow is:
  1. Script opens a real browser window
  2. Analyst logs into MenthorQ manually
  3. Analyst clicks once on the calendar to trigger a real POST request
  4. Playwright captures the nonce from that request and proceeds automatically

  This cannot run unattended, in Docker, or in any headless environment. It is inherently a manual-assist  
  workflow.

  ---
  10. Streamlit Viewer — Only Reflects Committed Data

  ic7_viewer.py is deployed on Streamlit Cloud and reads CSVs directly from the GitHub repository. It has  
  no access to:
  - The Google Drive parquet store
  - Any local data/ files

  The optional re-entry simulation in the viewer (try: import sys...) requires G:/Meu Drive/Quant_Data_MD/ 
  and silently disables itself when running in the cloud. An analyst running the viewer locally with Google
   Drive mounted gets more features than the deployed version — with no visible indicator that features are
   missing.

  False conclusion risk: An analyst using the cloud-deployed viewer may believe re-entry simulation is     
  unavailable or broken, when it only works locally.

  ---
  11. Windows Encoding — cp1252 Terminal Crashes

  Several scripts use Unicode characters (arrows →, box-drawing ═, ─) in print statements. On Windows      
  terminals with cp1252 encoding (default for many cmd/PowerShell sessions), these characters cause        
  UnicodeEncodeError crashes at runtime.

  This was discovered and partially fixed in thetadata_step1_download.py during development. It may still  
  affect other scripts that have not been tested on a non-UTF-8 terminal.

  ---
  12. API Keys — No Centralized Validation

  API keys live in .env (local) and GitHub Secrets (cloud). There is no startup validation that checks all 
  required keys are present before a script begins work. A script may run for several minutes, make many   
  API calls, and only fail late when it hits the missing key.

  Keys that must be maintained in two places (local .env AND GitHub Secrets):
  - PERPLEXITY_API_KEY
  - DISCORD_WEBHOOK_URL
  - FINNHUB_API_KEY

  If a key is rotated locally but not in GitHub Secrets (or vice versa), the morning briefing fails        
  silently in the cloud while working fine locally.

  ---
  13. Market Data App API — Single Key, No Rotation Plan

  The Market Data App API key is hardcoded directly in md_step2_mass_extractor.py and md_step1_extractor.py
   (not read from .env). If the key needs to be rotated, it must be updated in both script files manually. 

  The key also appears in the session transcript and git history if these scripts were ever committed with 
  the key present. This is a security exposure.

  ---
  14. data/ Directory Is Fully Gitignored

  The entire data/ directory is gitignored. This means:
  - ndx_closes_cache.csv is machine-local only
  - All Barchart GEX CSVs are machine-local only
  - menthorq_levels.csv is machine-local only
  - ibkr_contract_universe.parquet is machine-local only

  On a new machine, all these files must be regenerated from scratch. There is no documented procedure for 
  doing so in sequence.

  ---
  15. Legacy Databento Code — May Cause Confusion

  scripts/legacy_databento/ contains the original pipeline (ic7_simulator.py, db_step1_definition.py, etc.)
   that was replaced by the Market Data App pipeline. This code is not removed, not clearly marked as      
  deprecated in the directory structure, and ic7_simulator.py is named similarly to active scripts.        

  Migration risk: A new developer or AI system may attempt to use or integrate legacy Databento scripts,   
  which reference data formats and API endpoints that no longer apply to current operations.

  ---
  16. No SPX or RUT Backtest Viewer

  ic7_viewer.py is the only Streamlit-deployed dashboard. It reads NDX-specific CSVs. There is no
  equivalent viewer for:
  - SS42 (Short Strangle on SPX/RUT)
  - Any SPX or RUT Iron Condor variant

  SS42 results exist only as local CSV files with no visualization infrastructure.

  ---
  Migration Risks — Moving to Codex

  ┌────────────────┬───────────────────────────────────────────────────────────────────────────────────┐   
  │      Risk      │                                      Detail                                       │   
  ├────────────────┼───────────────────────────────────────────────────────────────────────────────────┤   
  │ Google Drive   │ G:/Meu Drive/Quant_Data_MD/ will not exist in any cloud sandbox. All parquet      │   
  │ paths          │ reads will fail. Parquets must be transferred to a path the new environment can   │   
  │                │ access.                                                                           │   
  ├────────────────┼───────────────────────────────────────────────────────────────────────────────────┤   
  │ No dependency  │ Codex cannot reconstruct the exact environment. pyarrow version matters — the     │   
  │ lockfile       │ existing workaround in load_chain handles one specific version conflict but       │   
  │                │ others may exist.                                                                 │   
  ├────────────────┼───────────────────────────────────────────────────────────────────────────────────┤   
  │ Hand-edited    │ Scripts use top-of-file constants instead of CLI args or config files. A code     │   
  │ configs        │ assistant will need to edit source to change behavior, increasing the risk of     │   
  │                │ accidental overwrite of working settings.                                         │   
  ├────────────────┼───────────────────────────────────────────────────────────────────────────────────┤   
  │ API key in     │ Market Data App key is in md_step2_mass_extractor.py. Codex will see it in        │   
  │ source code    │ context and may log or expose it. Should be moved to .env before migration.       │   
  ├────────────────┼───────────────────────────────────────────────────────────────────────────────────┤   
  │ Implicit       │ The correct execution order (cache → extractor → backtest → commit → push) is not │   
  │ workflow order │  encoded anywhere in the codebase. It lives only in documentation and operator    │   
  │                │ knowledge.                                                                        │   
  ├────────────────┼───────────────────────────────────────────────────────────────────────────────────┤   
  │ Windows line   │ Files edited on Windows may have CRLF endings. Some tools in Linux-based          │   
  │ endings        │ sandboxes handle this poorly.                                                     │   
  ├────────────────┼───────────────────────────────────────────────────────────────────────────────────┤   
  │ Silent skip    │ Most scripts skip missing data silently (no exception, just a continue). A new AI │   
  │ behavior       │  operator may interpret a successful zero-output run as correct behavior when     │   
  │                │ data is actually absent.                                                          │   
  └────────────────┴───────────────────────────────────────────────────────────────────────────────────┘