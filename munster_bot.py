import praw
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import os
import json
import re

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

        # Extract date/time (robust regex)
        date_match = re.search(r"(\w{3}\s\d{1,2}\s\w{3}\s\d{4}),?\s*(\d{2}:\d{2})?", text)
        if not date_match:
            continue

        date_str = f"{date_match.group(1)} {date_match.group(2) or '00:00'}"
        try:
            dt = datetime.strptime(date_str, "%a %d %b %Y %H:%M")
        except ValueError:
            continue

        # Skip past matches
        if dt < datetime.utcnow() - timedelta(days=1):
            continue

        # Extract teams
        teams_match = re.search(r"([A-Za-z\s]+)\s+vs\s+([A-Za-z\s]+)", text)
        teams = teams_match.group(0) if teams_match else TEAM_NAME

        matches.append({
            "teams": teams.strip(),
            "datetime": dt,
            "url": TEAM_URL
        })

    print(f"Found {len(matches)} future matches.")
    return matches

def get_today_match(matches):
    """Find a Munster match scheduled for today (UTC)."""
    now = datetime.utcnow()
    for match in matches:
        if 0 <= (match["datetime"] - now).total_seconds() < 86400:
            return match
    return None

def reddit_client():
    """Create a Reddit client using environment variables."""
    return praw.Reddit(
        client_id=os.getenv("REDDIT_CLIENT_ID"),
        client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
        username=os.getenv("REDDIT_USERNAME"),
        password=os.getenv("REDDIT_PASSWORD"),
        user_agent=os.getenv("USER_AGENT")
    )

def already_posted(match):
    """Check if a match has already been posted."""
    if not os.path.exists(MATCH_HISTORY_FILE):
        return False
    try:
        with open(MATCH_HISTORY_FILE) as f:
            data = json.load(f)
        return match["teams"] in data
    except Exception:
        return False

def save_posted(match):
    """Save match info to JSON log."""
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

def post_match_thread(match):
    """Post a match thread to Reddit."""
    reddit = reddit_client()
    subreddit = reddit.subreddit(SUBREDDIT)
    title = f"Match Thread: {match['teams']} ({match['datetime'].strftime('%Y-%m-%d %H:%M UTC')})"
    body = (
        f"**Kickoff:** {match['datetime'].strftime('%A %d %B %Y, %H:%M UTC')}\n\n"
        f"**Teams:** {match['teams']}\n\n"
        f"[More info on RugbyKickoff.com]({match['url']})\n\n"
        f"Up {TEAM_NAME}! 🔴"
    )
    subreddit.submit(title, selftext=body)
    print(f"✅ Posted: {title}")

# ---------------- MAIN LOGIC ----------------
if __name__ == "__main__":
    matches = get_munster_matches()
    if not matches:
        print("No matches found.")
        exit()

    today_match = get_today_match(matches)
    if today_match:
        post_time = get_post_time(today_match)
        now = datetime.utcnow()
        if now >= post_time and not already_posted(today_match):
            post_match_thread(today_match)
            save_posted(today_match)
        else:
            print(f"Match thread not posted yet. Scheduled post time: {post_time} UTC")
    else:
        print("No Munster match today or already posted.")
