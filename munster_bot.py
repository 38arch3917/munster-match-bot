import praw
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import os
import json
import re
import pytz

# ---------------- CONFIGURATION ----------------
TEAM_NAME = "Munster"
SUBREDDIT = "Munsterrugby"
MATCH_HISTORY_FILE = "posted.json"
TEAM_URL = "https://rugbykickoff.com/teams/munster/"
TIMEZONE = pytz.timezone("Europe/Dublin")
POST_FLAIR_ID = "44ddc6a8-a2a2-11f0-ab19-0257fc8eb3f2"
# ------------------------------------------------


def get_post_time(match):
    """Return IST datetime when match thread should post (4 hours before kickoff)."""
    return match["datetime"] - timedelta(hours=4)


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

    fixture_candidates = soup.select(".fixture, .match, .upcoming-fixture, li")
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
            dt = datetime.strptime(date_str, "%a %d %b %Y %H:%M")
            dt = pytz.utc.localize(dt).astimezone(TIMEZONE)
        except ValueError:
            continue

        # Skip past matches
        if dt < datetime.now(TIMEZONE) - timedelta(days=1):
            continue

        # Extract teams
        teams_match = re.search(r"([A-Za-z\s]+)\s+vs\.?\s+([A-Za-z\s]+)", text)
        teams = teams_match.group(0) if teams_match else TEAM_NAME

        # Extract venue
        venue_match = re.search(r"at\s([A-Za-z\s]+)", text)
        venue = venue_match.group(1).strip() if venue_match else "Venue TBC"

        # Extract competition
        comp_match = re.search(r"(URC|United Rugby Championship|Champions Cup|Challenge Cup)", text)
        competition = comp_match.group(1).replace("United Rugby Championship", "URC") if comp_match else "Fixture"

        matches.append({
            "teams": teams.strip(),
            "datetime": dt,
            "venue": venue,
            "competition": competition,
            "url": TEAM_URL
        })

    print(f"Found {len(matches)} future matches.")
    return matches


def get_today_match(matches):
    now = datetime.now(TIMEZONE)
    for match in matches:
        if 0 <= (match["datetime"] - now).total_seconds() < 86400:
            return match
    return None


def reddit_client():
    return praw.Reddit(
        client_id=os.getenv("REDDIT_CLIENT_ID"),
        client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
        username=os.getenv("REDDIT_USERNAME"),
        password=os.getenv("REDDIT_PASSWORD"),
        user_agent=os.getenv("USER_AGENT")
    )


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


def post_match_thread(match):
    reddit = reddit_client()
    subreddit = reddit.subreddit(SUBREDDIT)

    # Title example: [URC] Munster vs. Cardiff - Friday 10 Oct 2025 @ 19:00 (IST) - Thomond Park
    title = f"[{match['competition']}] {match['teams']} - {match['datetime'].strftime('%A %d %b %Y @ %H:%M')} (IST) - {match['venue']}"

    body = (
        f"🏉 **Match Thread: {match['teams']}**\n\n"
        f"**Kickoff:** {match['datetime'].strftime('%A %d %b %Y, %H:%M (IST)')}\n\n"
        f"**Venue:** {match['venue']}\n\n"
        f"**Competition:** {match['competition']}\n\n"
        f"---\n\n"
        f"### 🏉 Starting XV\n"
        f"*To be confirmed*\n\n"
        f"---\n\n"
        f"**Stand Up And Fight! 💪🔴**\n\n"
        f"*Posted by MunsterKickoff 🤖 – created by /u/i93*"
    )

    subreddit.submit(title, selftext=body, flair_id=POST_FLAIR_ID)
    print(f"✅ Posted: {title}")


if __name__ == "__main__":
    matches = get_munster_matches()
    if not matches:
        print("No matches found.")
        exit()

    today_match = get_today_match(matches)
    if today_match:
        post_time = get_post_time(today_match)
        now = datetime.now(TIMEZONE)
        if now >= post_time and not already_posted(today_match):
            post_match_thread(today_match)
            save_posted(today_match)
        else:
            print(f"Match not posted yet. Scheduled post time: {post_time.strftime('%Y-%m-%d %H:%M (IST)')}")
    else:
        print("No Munster match today or already posted.")
