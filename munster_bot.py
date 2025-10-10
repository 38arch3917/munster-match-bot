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
FORCE_POST = False  # <-- Set True for testing to post immediately
# ------------------------------------------------

# ---------------- TIMEZONE ----------------
IRISH_TZ = pytz.timezone("Europe/Dublin")
# ------------------------------------------------

def get_post_time(match):
    """Post 4 hours before kickoff (UTC)."""
    return match["datetime_utc"] - timedelta(hours=4)

def get_munster_matches():
    """Scrape ESPN for Munster fixtures (with debug)."""
    print("Fetching Munster fixtures from ESPN...")
    matches = []
    try:
        r = requests.get(TEAM_URL_ESPN, timeout=20)
        r.raise_for_status()
    except Exception as e:
        print(f"❌ Error fetching fixtures: {e}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    rows = soup.select("table tbody tr")

    for row in rows:
        cols = [c.get_text(" ", strip=True) for c in row.select("td")]
        if len(cols) < 4:
            continue

        date_str, opponent, comp, result = cols[0], cols[1], cols[2], cols[3]

        # Skip past matches
        if re.search(r"\d+-\d+", result):
            continue

        # Parse date and time
        date_match = re.search(r"(\w+),\s+(\w+)\s+(\d+),\s+(\d{4})", date_str)
        if not date_match:
            continue

        month = date_match.group(2)
        day = date_match.group(3)
        year = date_match.group(4)
        time_tag = row.select_one(".localtime")
        time_str = time_tag.get_text(strip=True) if time_tag else "19:00"

        try:
            dt_local = datetime.strptime(f"{day} {month} {year} {time_str}", "%d %b %Y %H:%M")
            dt_utc = IRISH_TZ.localize(dt_local).astimezone(pytz.utc)
        except Exception:
            continue

        matches.append({
            "teams": f"Munster vs. {opponent}" if "Munster" not in opponent else f"{opponent} vs. Munster",
            "competition": comp.strip(),
            "datetime_utc": dt_utc,
            "datetime_local": dt_local,
            "venue": "TBC",
            "url": TEAM_URL_ESPN
        })

    # Debug: print fetched fixtures
    print("📅 Upcoming fixtures:")
    for m in matches:
        print(f" - {m['teams']} | {m['datetime_local'].strftime('%A %d %b %Y %H:%M')} | {m['competition']}")

    print(f"✅ Found {len(matches)} future matches.")
    return matches

def get_today_match(matches):
    now = datetime.utcnow().replace(tzinfo=pytz.utc)
    for match in matches:
        if 0 <= (match["datetime_utc"] - now).total_seconds() < 86400:
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

    local_dt = match["datetime_local"]
    formatted_date = local_dt.strftime("%A %d %b %Y @ %H:%Mhrs (IST) - " + match["venue"])
    title = f"🏉 {match['competition']} | {match['teams']} | {formatted_date}"

    body = (
        f"**Kickoff:** {formatted_date}\n\n"
        f"**Competition:** {match['competition']}\n\n"
        f"**Venue:** {match['venue']}\n\n"
        f"**Starting XV ⚫🔴⚪**\n\n"
        f"(To be confirmed)\n\n"
        f"**Stand Up And Fight! 💪🔴**\n\n"
        f"*Automated by /u/MunsterKickoff 🤖*"
    )

    submission = subreddit.submit(title, selftext=body, flair_id=FLAIR_ID)
    submission.mod.distinguish(sticky=True)
    print(f"✅ Posted: {title}")

# ---------------- MAIN LOGIC ----------------
if __name__ == "__main__":
    matches = get_munster_matches()
    if not matches:
        print("❌ No matches found.")
        exit()

    today_match = get_today_match(matches)
    if today_match:
        post_time = get_post_time(today_match)
        now = datetime.utcnow().replace(tzinfo=pytz.utc)
        if FORCE_POST or (now >= post_time and not already_posted(today_match)):
            print("⚙️ Posting match thread (force mode or scheduled time)...")
            post_match_thread(today_match)
            save_posted(today_match)
        else:
            print(f"🕐 Match thread not posted yet. Scheduled post time: {post_time.strftime('%Y-%m-%d %H:%M UTC')}")
    else:
        print("ℹ️ No Munster match today or already posted.")
