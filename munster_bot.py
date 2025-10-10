import praw
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import os
import json
import pytz
import re

# ---------------- CONFIG ----------------
SUBREDDIT = "Munsterrugby"
FLAIR_ID = "44ddc6a8-a2a2-11f0-ab19-0257fc8eb3f2"
IRISH_TZ = pytz.timezone("Europe/Dublin")

# Next match manually added
next_match = {
    "teams": "Edinburgh vs. Munster",
    "competition": "URC",
    "datetime_local": IRISH_TZ.localize(datetime(2025,10,10,19,0)),
    "venue": "Murrayfield Stadium",
import praw
import requests
from datetime import datetime, timedelta
import pytz
import os
import json

# ---------------- CONFIG ----------------
TEAM_NAME = "Munster"
SUBREDDIT = "Munsterrugby"
MATCH_HISTORY_FILE = "posted.json"
FLAIR_ID = "44ddc6a8-a2a2-11f0-ab19-0257fc8eb3f2"  # Match Thread 🔴
RUGBYKICKOFF_API = "https://www.rugbykickoff.com/api/teams/munster/fixtures"
TEST_MODE = False  # Set True to force post immediately
IRISH_TZ = pytz.timezone("Europe/Dublin")
# ----------------------------------------

def get_post_time(match):
    """Return the UTC datetime to post the thread (4 hours before kickoff)."""
    return match["datetime_utc"] - timedelta(hours=4)

def get_munster_matches():
    """Fetch Munster fixtures from RugbyKickoff API."""
    print("Fetching Munster fixtures from RugbyKickoff API...")
    matches = []
    try:
        r = requests.get(RUGBYKICKOFF_API, timeoutatch_thread(next_match)
