import praw
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import os
import json
import re
import sys

# ---------------- CONFIGURATION ----------------
TEAM_NAME = "Munster"  # Team to track
SUBREDDIT = "Munsterrugby"  # Where to post
MATCH_HISTORY_FILE = "posted.json"  # Log of posted matches
TEAM_URL = "https://rugbykickoff.com/teams/munster/"  # Source URL
# ------------------------------------------------

# ---------------- POST TIME LOGIC ----------------
def get_post_time(match):
    """Return the UTC datetime when the match thread should be posted (4 hours before kickoff)."""
    return match["datetime"] - timedelta(hours=4)
# -------------------------------------------------

def get_munster_matches():
    """Scrape rugbykickoff.com for Munster fixtures."""
    print("Fetching Munster fixtures...")
    try:
        r = requests.get(TEAM_URL, timeout=20)
        r.raise_for_status()
    except Exception as e:
        print(f"Error fetching fixtures: {e}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    matches = []

    fixture_candidates = soup.select(".fixture, .match, .upcoming-fixture, li") or []

    for fixture in fixture_candidates:
        text = fixture.get_text(" ", strip=True)
        if TEAM_NAME.lower() not in text.lower():
            continue

        # Extract date/time
        date_match = re.search(r"(\w{3}\s\d{1,2}\s\w{3}\s\d{4}),?\s*(\d{2}:\d{2})?", text)
        if not date_match:
            continue

        date_str = f"{date_match.group(1)} {date_match.group(2) or '00:00'}"
        try:
            dt = datetime.strptime
