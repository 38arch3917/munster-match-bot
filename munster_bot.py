import praw
import requests
from datetime import datetime, timedelta
import os
import json
import pytz

# ---------------- CONFIGURATION ----------------
TEAM_NAME = "Munster"
SUBREDDIT = "Munsterrugby"
MATCH_HISTORY_FILE = "posted.json"
FLAIR_ID = "44ddc6a8-a2a2-11f0-ab19-0257fc8eb3f2"  # 'Match Thread 🔴'
RUGBYKICKOFF_JSON = "https://www.rugbykickoff.com/api/teams/munster/fixtures"
TEST_MODE = True  # Set True to force a post for debugging
# ------------------------------------------------

IRISH_TZ = pytz.timezone("Europe/Dublin")

def reddit_client():
    return praw.Reddit(
        client_id=os.getenv("REDDIT_CLIENT_ID"),
        client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
        username=os.getenv("REDDIT_USERNAME"),
        password=os.getenv("REDDIT_PASSWORD"),
        user_agent=os.getenv("USER_AGENT")
    )

def get_post_time(match):
    """Post 4 hours before kickoff UTC."""
    return match["datetime_utc"] - timedelta(hours=4)

def already_posted(match):
    if not os.path.exists(MATCH_HISTORY_FILE):
        return False
    try:
        with open(MATCH_HISTORY_FILE) as f:
            data = json.load(f)
        return match["teams"] in data
    except Exception:
        return False

def save_posted(match):
    data = []
    if os.path.exists(MATCH_HISTORY_FILE):
        with open(MATCH_HISTORY_FILE) as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                data = []
    data.append(match["teams"])
    with open(MATCH_HISTORY_FILE, "w") as f:
        json.dump(data, f)

def get_munster_matches():
    """Fetch Munster fixtures from RugbyKickoff JSON API."""
    print("Fetching Munster fixtures from RugbyKickoff API...")
    matches = []
    try:
        r = requests.get(RUGBYKICKOFF_JSON,
