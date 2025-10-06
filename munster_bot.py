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
COMPETITION_ABBREV = {
    "United Rugby Championship": "URC",
    "European Rugby Champions Cup": "ERCC"
}
FLAIR_ID = "44ddc6a8-a2a2-11f0-ab19-0257fc8eb3f2"  # 'Match Thread 🔴' flair
# ------------------------------------------------

def get_post_time(match):
    return match["datetime"] - timedelta(hours=4)

def get_munster_matches():
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

        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
        if dt < datetime.now(ZoneInfo("UTC")) - timedelta(days=1):
            continue

        teams_match = re.search(r"([A-Za-z\s]+)\s+vs\s+([A-Za-z\s]+)", text)
        teams = teams_match.group(0) if teams_match else TEAM_NAME

        venue_match = re.search(r"at\s+([A-Za-z\s\-,]+)", text)
        if not venue_match:
            venue_match = re.search(r"\(([A-Za-z\s\-,]+)\)", text)
        venue = venue_match.group(1).strip() if venue_match else None

        if not venue:
            parts = teams.lower().split("vs")
            if parts and parts[0].strip() == TEAM_NAME.lower():
                venue = "Thomond Park"
            else:
                venue = "Venue TBC"

        comp_match = re.search(r"(United Rugby Championship|URC|European Rugby Champions Cup|ERCC)", text, re.I)
        competition = COMPETITION_ABBREV.get(comp_match.group(1), comp_match.group(1)) if comp_match else "Other"

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
    now = datetime.now(ZoneInfo("UTC"))
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

# ---------------- LINEUP FETCH ----------------
def fetch_espn_lineups(game_id):
    try:
        if not game_id:
            return None, None
        url = f"https://www.espn.com/rugby/lineups/_/gameId/{game_id}"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        starters = soup.select(".lineup__wrapper .starter")
        if not starters:
            starters = soup.select("table td, table tr")
        names = [el.get_text(strip=True) for el in starters if el.get_text(strip=True)]
        if len(names) < 2:
            return None, None
        half = len(names)//2
        return names[:half], names[half:]
    except Exception as e:
        print(f"ESPN lineup fetch failed: {e}")
        return None, None

def fetch_ultimate_rugby_lineups(match):
    try:
        team_slug = match["teams"].split(" vs ")[0].lower().replace(" ", "-")
        url = f"https://www.ultimaterugby.com/{team_slug}/fixtures"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        return None, None  # placeholder for actual parsing
    except Exception as e:
        print(f"Ultimate Rugby fetch failed: {e}")
        return None, None

def fetch_starting_xv(game_id, match):
    home, away = fetch_espn_lineups(game_id)
    if home and away:
        return home, away
    return fetch_ultimate_rugby_lineups(match)

def format_lineup_table(home_list, away_list, home_name, away_name):
    lines = []
    lines.append(f"| {home_name} | {away_name} |")
    lines.append("|---|---|")
    for h, a in zip(home_list, away_list):
        lines.append(f"| {h} | {a} |")
    return "\n".join(lines)
# ---------------------------------------------

def post_match_thread(match):
    try:
        reddit = reddit_client()
        subreddit = reddit.subreddit(SUBREDDIT)

        kickoff_local = match["datetime"].astimezone(IRELAND_TZ)

        game_id = None
        home, away = fetch_starting_xv(game_id, match)

        teams = match["teams"].replace("vs", "vs.").strip()
        parts = teams.split(" vs.")
        home_name = parts[0].strip() if len(parts) >= 2 else "Team A"
        away_name = parts[1].strip() if len(parts) >= 2 else "Team B"

        if home and away:
            starting_xv_md = format_lineup_table(home, away, home_name, away_name)
        else:
            starting_xv_md = "_Starting XV to be confirmed closer to kickoff._"

        title = (
            f"Match Thread: {match['teams'].replace('vs', 'vs.')} – "
            f"{match['competition']} – "
            f"{kickoff_local.strftime('%a %d %b %Y @ %H:%Mhrs (IST)')} – "
            f"{match['venue']}"
        )

        body = (
            f"**Competition:** {match['competition']}\n"
            f"**Kickoff:** {kickoff_local.strftime('%a %d %b %Y, %H:%M (IST)')} – {match['venue']}\n\n"
            f"**Teams:** {match['teams'].replace('vs', 'vs.').strip()}\n\n"
            f"**Starting XV:**\n{starting_xv_md}\n\n"
            f"Up {TEAM_NAME}! 🔴"
        )

        # Submit the post
        submission = subreddit.submit(title, selftext=body)

        # Assign the flair using the provided flair ID
        submission.flair.select(FLAIR_ID)

        print(f"✅ Posted with flair 'Match Thread 🔴': {title}")

    except Exception as e:
        print(f"❌ Error posting to Reddit: {e}")
        sys.exit(1)

# ---------------- MAIN ----------------
if __name__ == "__main__":
    matches = get_munster_matches()
    if not matches:
        print("No matches found today.")
        exit()

    print("\nUpcoming Munster matches today:")
    for m in matches:
        kickoff_local = m["datetime"].astimezone(IRELAND_TZ)
        print(f"- {m['teams']} | Competition: {m['competition']} | Kickoff: {kickoff_local.strftime('%a %d %b %Y %H:%M (IST)')} | Venue: {m['venue']}")

    today_match = get_today_match(matches)
    if today_match:
        post_time = get_post_time(today_match)
        now = datetime.now(ZoneInfo("UTC"))
        post_time_local = post_time.astimezone(IRELAND_TZ)
        print(f"\nToday's match scheduled for posting:")
        print(f"- {today_match['teams']} | Competition: {today_match['competition']} | Scheduled post time: {post_time_local.strftime('%a %d %b %Y %H:%M (IST)')} | Venue: {today_match['venue']}")

        if now >= post_time and not already_posted(today_match):
            post_match_thread(today_match)
            save_posted(today_match)
        else:
            print("Match thread not posted yet (waiting for post time or already posted).")
    else:
        print("\nNo Munster match today or already posted.")
