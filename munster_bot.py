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

        # Extract date/time
        date_match = re.search(r"(\w{3}\s\d{1,2}\s\w{3}\s\d{4}),?\s*(\d{2}:\d{2})?", text)
        if not date_match:
            continue

        date_str = f"{date_match.group(1)} {date_match.group(2) or '00:00'}"
        try:
            dt = datetime.strptime(date_str, "%a %d %b %Y %H:%M")
        except ValueError:
            continue

        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
        if dt < datetime.now(ZoneInfo("UTC")) - timedelta(days=1):
            continue

        # Extract teams
        teams_match = re.search(r"([A-Za-z\s]+)\s+vs\s+([A-Za-z\s]+)", text)
        teams = teams_match.group(0) if teams_match else TEAM_NAME

        # Extract venue (try multiple patterns)
        venue_match = re.search(r"at\s+([A-Za-z\s\-,]+)", text)
        if not venue_match:
            venue_match = re.search(r"\(([A-Za-z\s\-,]+)\)", text)
        venue = venue_match.group(1).strip() if venue_match else None

        # Auto-detect home venue
        if not venue:
            # If “Munster vs X” and Munster is first, assume home
            parts = teams.lower().split("vs")
            if parts and parts[0].strip() == TEAM_NAME.lower():
                venue = "Thomond Park"
            else:
                venue = "Venue TBC"

        matches.append({
            "teams": teams.strip(),
            "datetime": dt,
            "venue": venue,
            "url": TEAM_URL
        })

    print(f"Found {len(matches)} future matches.")
    return matches

def get_today_match(matches):
    """Find a Munster match scheduled for today (UTC)."""
    now = datetime.now(ZoneInfo("UTC"))
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

def fetch_espn_lineups(game_id):
    """
    Try to fetch lineups from ESPN using the “lineups” URL pattern.
    This is experimental.
    """
    try:
        # Example ESPN lineups page: `/lineups/_/gameId/599267/league/270557` as seen in community gists 0
        url = f"https://www.espn.com/rugby/lineups/_/gameId/{game_id}"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # ESPN lineup pages often have two blocks, each for one team:
        # We search for table or list of players under "Starters" headers
        # This is approximate and may break if HTML changes
        starters = soup.select(".lineup__wrapper .starter")  # CSS guessed
        # fallback: look for table rows
        if not starters:
            starters = soup.select("table td, table tr")

        # Parse starters text
        # For simplicity: group half for home, half for away
        names = [el.get_text(strip=True) for el in starters if el.get_text(strip=True)]
        if len(names) < 2:
            return None, None

        half = len(names) // 2
        home = names[:half]
        away = names[half:]
        return home, away

    except Exception as e:
        print(f"Error fetching ESPN lineups: {e}")
        return None, None

def format_lineup_table(home_list, away_list, home_name, away_name):
    """Format two lists of players side by side as a markdown table."""
    lines = []
    lines.append(f"| {home_name} | {away_name} |")
    lines.append("|---|---|")
    for h, a in zip(home_list, away_list):
        lines.append(f"| {h} | {a} |")
    return "\n".join(lines)

def post_match_thread(match):
    """Post a match thread to Reddit."""
    try:
        reddit = reddit_client()
        subreddit = reddit.subreddit(SUBREDDIT)

        kickoff_local = match["datetime"].astimezone(IRELAND_TZ)

        # Try to extract a game_id from the URL or teams (you may need to improve this)
        game_id = None
        # You might parse match["url"] or match["teams"] to get a numeric id
        # For now leave game_id = None

        # Try ESPN lineups
        home, away = None, None
        if game_id:
            home, away = fetch_espn_lineups(game_id)

        if home and away:
            teams = match["teams"].replace("vs", "vs.").strip()
            parts = teams.split(" vs.")
            if len(parts) >= 2:
                home_name = parts[0].strip()
                away_name = parts[1].strip()
            else:
                home_name = "Team A"
                away_name = "Team B"
            lineup_md = format_lineup_table(home, away, home_name, away_name)
        else:
            lineup_md = "_Lineups to be confirmed closer to kickoff._"

        title = (
            f"Match Thread: {match['teams'].replace('vs', 'vs.')} – "
            f"{kickoff_local.strftime('%a %d %b %Y @ %H:%Mhrs (Irish Time)')} – "
            f"{match['venue']}"
        )

        body = (
            f"**Kickoff:** {kickoff_local.strftime('%a %d %b %Y, %H:%M (Irish Time)')} – {match['venue']}\n\n"
            f"**Teams:** {match['teams'].replace('vs', 'vs.').strip()}\n\n"
            f"**Lineups:**\n{lineup_md}\n\n"
            f"[More info on RugbyKickoff.com]({match['url']})\n\n"
            f"Up {TEAM_NAME}! 🔴"
        )

        subreddit.submit(title, selftext=body)
        print(f"✅ Posted: {title}")

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
        now = datetime.now(ZoneInfo("UTC"))
        if now >= post_time and not already_posted(today_match):
            post_match_thread(today_match)
            save_posted(today_match)
        else:
            print(f"Match thread not posted yet. Scheduled post time: {post_time.astimezone(IRELAND_TZ).strftime('%a %d %b %Y %H:%M (Irish Time)')}")
    else:
        print("No Munster match today or already posted.")
