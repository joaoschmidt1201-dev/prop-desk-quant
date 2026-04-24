"""
db_kill_job.py — Emergency job cancellation
Cancels Databento batch job OPRA-20260331-F4LA6NBTK4
"""

import os
import sys
from dotenv import load_dotenv
import databento as db

ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
load_dotenv(ENV_PATH)

API_KEY = os.getenv("DATABENTO_API_KEY")
JOB_ID  = "OPRA-20260331-F4LA6NBTK4"

if not API_KEY:
    print("ERROR: DATABENTO_API_KEY not found in .env")
    sys.exit(1)

BASE_URL = "https://hist.databento.com/v0"

print(f"Attempting to cancel job: {JOB_ID}")

import requests

# Databento uses HTTP Basic Auth: API key as username, empty password
response = requests.post(
    f"{BASE_URL}/batch.cancel",
    auth=(API_KEY, ""),
    data={"job_id": JOB_ID},
    timeout=15,
)

print(f"HTTP Status : {response.status_code}")
print(f"Response    : {response.text}")

if response.status_code in (200, 202):
    print("SUCCESS — Cancellation request accepted.")
else:
    print("WARNING — Check response above for details.")
    sys.exit(1)
