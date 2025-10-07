import praw
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import os
import re
import pytz
import json

# ---------------- CONFIG ----------------
TEAM_NAME = "Munster"
SUBREDDIT = "Munsterrugby"
MATCH_HISTORY_FILE = "posted.json"
TEAM_URL = "https://rugbykickoff.com/teams/munster/"
TIMEZONE = pytz.timezone("Europe/Dublin")

def reddit_client():
    """Connect to Reddit using secrets."""
    return praw.Reddit(
        client_id=os.getenv("REDDIT_CLIENT_ID"),
        client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
        username=os.getenv("REDDIT_USERNAME"),
        password=os.getenv("REDDIT_PASSWORD"),
        user_agent=os.getenv("USER_AGENT")
    )

def get_posted_matches():
    if not os.path.exists(MATCH_HISTORY_FILE):
        return []
    with open(MATCH_HISTORY_FILE) as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []

def fetch_latest_results():
    """Scrape RugbyKickoff for Munster's most recent completed match."""
    r = requests.get(TEAM_URL)
    soup = BeautifulSoup(r.text, "html.parser")

    recent_match = None
    for item in soup.find_all(["li", "div"], text=re.compile(r"\bMunster\b", re.I)):
        text = item.get_text(" ", strip=True)
        if re.search(r"\d+\s*-\s*\d+", text):  # match score found
            recent_match = text
            break

    if not recent_match:
        return None

    score_match = re.search(r"([A-Za-z\s]+)\s(\d+)\s*-\s*(\d+)\s([A-Za-z\s]+)", recent_match)
    if not score_match:
        return None

    team1, score1, score2, team2 = score_match.groups()
    return {
        "team1": team1.strip(),
        "score1": score1,
        "score2": score2,
        "team2": team2.strip()
    }

def update_reddit_post(score_data):
    reddit = reddit_client()
    subreddit = reddit.subreddit(SUBREDDIT)
    title_search = f"Match Thread: {TEAM_NAME}"

    for post in subreddit.new(limit=10):
        if title_search in post.title and "FT:" not in post.title:
            ft_title = f"🏉 FT: {score_data['team1']} {score_data['score1']} - {score_data['score2']} {score_data['team2']}"
            post.edit(f"{ft_title}\n\n---\n\n{post.selftext}")
            post.mod.flair(text="Match Thread 🔴")
            post.mod.update(title=ft_title)
            print(f"✅ Updated: {post.title}")
            break

if __name__ == "__main__":
    print("🔍 Checking for final scores...")
    result = fetch_latest_results()
    if result:
        update_reddit_post(result)
    else:
        print("⚠️ No final score found yet.")
