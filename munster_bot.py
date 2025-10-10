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
API_URL = "https://www.rugbykickoff.com/api/teams/munster/fixtures"
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

def get_post_time(match):
    """Return the UTC datetime when the match thread should be posted (4 hours before kickoff)."""
    return match["datetime_utc"] - timedelta(hours=4)

def get_munster_matches():
    """Fetch Munster fixtures from RugbyKickoff JSON API."""
    print("Fetching Munster fixtures from RugbyKickoff API...")
    matches = []
    try:
        r = requests.get(API_URL, timeout=20)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"❌ Error fetching fixtures: {e}")
        return []

    for item in data.get("fixtures", []):
        try:
            opponent = item.get("opponent", "TBC")
            comp = item.get("competition", "Unknown Competition")
            venue = item.get("venue", "TBC")
            date_str = item.get("dateTime")
            if not date_str:
                continue

            dt_utc = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            dt_local = dt_utc.astimezone(IRISH_TZ)

            if dt_utc < datetime.utcnow().replace(tzinfo=pytz.utc):
                continue

            matches.append({
                "teams": f"Munster vs. {opponent}" if "Munster" not in opponent else f"{opponent} vs. Munster",
                "competition": comp,
                "datetime_utc": dt_utc,
                "datetime_local": dt_local,
                "venue": venue,
                "url": "https://www.rugbykickoff.com/team/munster/"
            })
        except Exception:
            continue

    print(f"✅ Found {len(matches)} future matches.")
    # Print all upcoming fixtures for debugging
    for m in matches:
        print(f" - {m['teams']} | {m['datetime_local'].strftime('%A %d %b %Y %H:%M')} | {m['competition']}")
    return matches

def get_today_match(matches):
    now = datetime.utcnow().replace(tzinfo=pytz.utc)
    for match in matches:
        if 0 <= (match["datetime_utc"] - now).total_seconds() < 86400:
            return match
    return None

def post_match_thread(match, force_post=False):
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

    if force_post or not already_posted(match):
        submission = subreddit.submit(title, selftext=body, flair_id=FLAIR_ID)
        submission.mod.distinguish(sticky=True)
        print(f"✅ Posted: {title}")
        save_posted(match)
    else:
        print("ℹ️ Match already posted.")

# ---------------- MAIN ----------------
if __name__ == "__main__":
    matches = get_munster_matches()
    if not matches:
        print("❌ No matches found.")
        exit()

    # Debug: force post for testing
    today_match = get_today_match(matches)
    if today_match:
        post_time = get_post_time(today_match)
        now = datetime.utcnow().replace(tzinfo=pytz.utc)
        if now >= post_time:
            post_match_thread(today_match)
        else:
            print(f"🕐 Scheduled post time not reached: {post_time.strftime('%Y-%m-%d %H:%M UTC')}")
    else:
        print("ℹ️ No Munster match today or already posted.")

    # Optional: test post immediately
    # Uncomment next line to force a test post
    # post_match_thread(matches[0], force_post=True)
