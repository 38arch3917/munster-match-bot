import praw
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import os
import json
import pytz
import re

# ---------------- CONFIGURATION ----------------
TEAM_NAME = "Munster"
SUBREDDIT = "Munsterrugby"
MATCH_HISTORY_FILE = "posted.json"
TEAM_URL_ESPN = "https://www.espn.com/rugby/team/fixtures/_/id/228"
FLAIR_ID = "44ddc6a8-a2a2-11f0-ab19-0257fc8eb3f2"  # 'Match Thread 🔴'
# ------------------------------------------------

# ---------------- TIMEZONE ----------------
IRISH_TZ = pytz.timezone("Europe/Dublin")
# ------------------------------------------------

def get_post_time(match):
    """Post 4 hours before kickoff (UTC)."""
    return match["datetime_utc"] - timedelta(hours=4)

def get_munster_matches():
    """Scrape ESPN for Munster fixtures."""
    print("Fetching Munster fixtures from ESPN...")
    matches = []
    try:
        r = requests.get(TEAM_URL_ESPN
