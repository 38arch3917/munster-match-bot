import praw
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import os
import re
import pytz

TEAM_NAME = "Munster"
SUBREDDIT = "Munsterrugby"
TEAM_URL = "https://rugbykickoff.com/teams/munster/"
TIMEZONE = pytz.timezone("Europe/Dublin")

def reddit_client():
    return praw.Reddit(
        client_id=os.getenv("REDDIT_CLIENT_ID"),
        client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
        username=os.getenv("REDDIT_USERNAME"),
        password=os.getenv("REDDIT_PASSWORD"),
        user_agent=os.getenv("USER_AGENT")
    )

def fetch_latest_result():
    """Scrape RugbyKickoff for Munster’s most recent completed match."""
    try:
        r = requests.get(TEAM_URL, timeout=20)
        r.raise_for_status()
    except Exception as e:
        print(f"Error fetching: {e}")
        return None

    soup = BeautifulSoup(r.text, "html.parser")
    text = soup.get_text(" ", strip=True)
    score_match = re.search(r"([A-Za-z\s]+)\s(\d+)\s*-\s*(\d+)\s([A-Za-z\s]+)", text)

    if not score_match:
        print("No final score found.")
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

    for post in subreddit.new(limit=10):
        if TEAM_NAME in post.title and "FT:" not in post.title:
            ft_line = f"🏉 FT: {score_data['team1']} {score_data['score1']} - {score_data['score2']} {score_data['team2']}"
            new_body = f"{ft_line}\n\n---\n\n{post.selftext}"
            post.edit(new_body)
            print(f"✅ Updated: {post.title}")
            break

if __name__ == "__main__":
    print("🔍 Checking for final scores...")
    result = fetch_latest_result()
    if result:
        update_reddit_post(result)
    else:
        print("⚠️ No result available.")
