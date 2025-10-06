import praw
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import os
import json
import re
import sys

# ---------------- CONFIGURATION ----------------
TEAM_NAME = "Munster"
SUBREDDIT = "Munsterrugby"
MATCH_HISTORY_FILE = "posted.json"
TEAM_URL = "https://rugbykickoff.com/teams/munster/"
IRELAND_TZ = ZoneInfo("Europe/Dublin")
FLAIR_ID = "44ddc6a8-a2a2-11f0-ab19-0257fc8eb3f2"  # 'Match Thread 🔴' flair
# ------------------------------------------------

def get_post_time(match):
    """Return the UTC datetime when the match thread should be posted (4 hours before kickoff)."""
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
    fixture_candidates = soup.select(".fixture, .match, .upcoming-fixture, li") or []

    for fixture in fixture_candidates:
        text = fixture.get_text(" ", strip=True)
        if TEAM_NAME.lower() not in text.lower():
            continue

        date_match = re.search(r"(\w{3}\s\d{1,2}\s\w{3}\s\d{4}),?\s*(\d{2}:\d{2})?", text)
        if not date_match:
            continue

        date_str = f"{date_match.group(1)} {date_match.group(2) or '00:00'}"
        try:
            dt = datetime.strptime(date_str, "%a %d %b %Y %H:%M")
        except ValueError:
            continue

        if dt < datetime.utcnow() - timedelta(days=1):
            continue

        teams_match = re.search(r"([A-Za-z\s]+)\s+vs\s+([A-Za-z\s]+)", text)
        teams = teams_match.group(0) if teams_match else TEAM_NAME

        # Try to extract venue and competition
        venue = "TBC"
        comp = "Unknown"
        venue_match = re.search(r"Venue:\s*([A-Za-z\s]+)", text)
        if venue_match:
            venue = venue_match.group(1).strip()

        if "URC" in text or "United Rugby Championship" in text:
            comp = "URC"
        elif "Champions Cup" in text:
            comp = "Champions Cup"
        elif "Friendly" in text or "Pre-Season" in text:
            comp = "Friendly"

        # Try to find broadcasters
        broadcasters = []
        bcast_section = soup.find(text=re.compile("Broadcast", re.I))
        if bcast_section and bcast_section.parent:
            siblings = bcast_section.parent.find_next_siblings("span", limit=3)
            for s in siblings:
                b = s.get_text(strip=True)
                if b:
                    broadcasters.append(b)
        broadcasters_text = ", ".join(broadcasters) if broadcasters else "TBC"

        matches.append({
            "teams": teams.strip(),
            "datetime": dt,
            "venue": venue,
            "competition": comp,
            "broadcasters": broadcasters_text,
            "url": TEAM_URL
        })

    print(f"Found {len(matches)} future matches.")
    return matches

def get_today_match(matches):
    now = datetime.utcnow()
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

def format_starting_xv(home_name, away_name, home_players, away_players):
    """Format the Starting XV in preformatted block style for Reddit."""
    lines = []
    lines.append(f"{home_name:<15} {'#':^5} {away_name:>15}")
    for i in range(15):
        h = home_players[i] if i < len(home_players) else ""
        a = away_players[i] if i < len(away_players) else ""
        lines.append(f"{h:<15} {i+1:^5} {a:>15}")
    return "```\n" + "\n".join(lines) + "\n```"

def post_match_thread(match):
    """Post a match thread to Reddit with flair."""
    try:
        reddit = reddit_client()
        subreddit = reddit.subreddit(SUBREDDIT)

        kickoff_local = match["datetime"].astimezone(IRELAND_TZ)
        teams = match["teams"].replace("vs", "vs.").strip()
        parts = teams.split(" vs.")
        home_name = parts[0].strip() if len(parts) >= 2 else "Munster"
        away_name = parts[1].strip() if len(parts) >= 2 else "Opponent"

        # Placeholder player names until lineup scraping is added
        home_players = [f"Player {i}" for i in range(1, 16)]
        away_players = [f"Player {chr(64+i)}" for i in range(1, 16)]

        starting_xv_md = format_starting_xv(home_name, away_name, home_players, away_players)

        title = (
            f"Match Thread: {match['teams'].replace('vs', 'vs.')} – "
            f"{match['competition']} – "
            f"{kickoff_local.strftime('%a %d %b %Y @ %H:%Mhrs (IST)')} – "
            f"{match['venue']}"
        )

        body = (
            f"**Competition:** {match['competition']}\n"
            f"**Kickoff:** {kickoff_local.strftime('%a %d %b %Y, %H:%M (IST)')} – {match['venue']}\n"
            f"**Broadcasters:** {match['broadcasters']}\n\n"
            f"**Teams:** {match['teams'].replace('vs', 'vs.').strip()}\n\n"
            f"**Starting XV:**\n{starting_xv_md}\n\n"
            f"**Stand Up And Fight! 💪🔴**"
        )

        submission = subreddit.submit(title, selftext=body)
        submission.flair.select(FLAIR_ID)

        print(f"✅ Posted with flair: {title}")

    except Exception as e:
        print(f"❌ Error posting to Reddit: {e}")
        sys.exit(1)

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
