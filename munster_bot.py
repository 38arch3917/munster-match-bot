import os
import json
import requests
from datetime import datetime, timedelta
import pytz
from bs4 import BeautifulSoup
import praw
import re

# ---------------- CONFIG ----------------
TEAM_NAME = "Munster"
SUBREDDIT = "Munsterrugby"
MATCH_HISTORY_FILE = "posted.json"
POST_BEFORE_HOURS = 4
FLAIR_ID = "44ddc6a8-a2a2-11f0-ab19-0257fc8eb3f2"
HEADERS = {"User-Agent": "Mozilla/5.0"}
IST = pytz.timezone("Europe/Dublin")
RUGBY_KICKOFF_FIXTURES = "https://www.rugbykickoff.com/munster"
BROADCASTERS_WHITELIST = ["Premier Sports", "TG4", "RTÉ 2", "Access Munster", "URC.tv"]
# ---------------------------------------

# ---------------- HELPERS ----------------
def safe_get(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        return r.text
    except Exception as e:
        print(f"❌ Error fetching URL {url}: {e}")
        return None

def already_posted(url):
    if not os.path.exists(MATCH_HISTORY_FILE):
        return False
    try:
        with open(MATCH_HISTORY_FILE) as f:
            data = json.load(f)
        return url in data
    except:
        return False

def save_posted(url):
    data = []
    if os.path.exists(MATCH_HISTORY_FILE):
        try:
            with open(MATCH_HISTORY_FILE) as f:
                data = json.load(f)
        except:
            data = []
    data.append(url)
    with open(MATCH_HISTORY_FILE, "w") as f:
        json.dump(data, f)

def parse_datetime_kickoff(dt_str):
    """
    Parses strings like 'Sat 18 Oct 2025 17:15 IST' into a timezone-aware datetime.
    """
    try:
        dt_naive = datetime.strptime(dt_str.strip(), "%a %d %b %Y %H:%M %Z")
        dt_aware = IST.localize(dt_naive)
        return dt_aware
    except:
        return None

# ---------------- SCRAPING ----------------
def find_next_match():
    html = safe_get(RUGBY_KICKOFF_FIXTURES)
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")
    
    # Look for fixture rows
    fixtures = soup.select("div.fixture-row")  # assume div.fixture-row contains each match
    for f in fixtures:
        try:
            home = f.select_one(".team-home").get_text(strip=True)
            away = f.select_one(".team-away").get_text(strip=True)
            date_str = f.select_one(".kickoff").get_text(strip=True)  # e.g., "Sat 18 Oct 2025 17:15 IST"
            kickoff = parse_datetime_kickoff(date_str)
            venue = f.select_one(".venue").get_text(strip=True) if f.select_one(".venue") else "TBC"
            competition = f.select_one(".competition").get_text(strip=True) if f.select_one(".competition") else "URC"
            url_tag = f.select_one("a")
            match_url = url_tag["href"] if url_tag and url_tag.get("href") else RUGBY_KICKOFF_FIXTURES
            
            if already_posted(match_url):
                continue
            
            broadcasters = []
            b_tags = f.select(".broadcaster")
            for b in b_tags:
                name = b.get_text(strip=True)
                if name in BROADCASTERS_WHITELIST:
                    broadcasters.append(name)
            if not broadcasters:
                broadcasters = BROADCASTERS_WHITELIST
            
            return {
                "url": match_url,
                "home": home,
                "away": away,
                "datetime": kickoff,
                "venue": venue,
                "competition": competition,
                "broadcasters": broadcasters
            }
        except Exception as e:
            continue
    return None

# ---------------- REDDIT ----------------
def reddit_client():
    return praw.Reddit(
        client_id=os.getenv("REDDIT_CLIENT_ID"),
        client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
        username=os.getenv("REDDIT_USERNAME"),
        password=os.getenv("REDDIT_PASSWORD"),
        user_agent=os.getenv("USER_AGENT") or "MunsterKickoffBot/1.0"
    )

def post_match_thread(match):
    reddit = reddit_client()
    subreddit = reddit.subreddit(SUBREDDIT)

    dt_ist = match["datetime"].astimezone(IST) if match["datetime"] else None
    date_str = dt_ist.strftime("%a %d %b %Y") if dt_ist else "TBC"
    time_str = dt_ist.strftime("%H:%M") if dt_ist else "TBC"

    title = f"Match Thread: {match['home']} vs {match['away']} ({match['competition']}) - {date_str} {time_str} - {match['venue']}"

    body_lines = [
        f"🕒 **Kickoff:** {time_str} IST",
        f"📍 **Venue:** {match['venue']}",
        f"🏆 **Competition:** {match['competition']}",
        f"📺 **Broadcasters:** {', '.join(match['broadcasters'])}",
        "🏉 **Starting XV:**\n> Will be announced 1–2 days before kickoff.",
        "\n**Stand Up And Fight! 💪🔴**",
        "\n*Automated by /u/MunsterKickoff using rugbykickoff.com*"
    ]

    body = "\n\n".join(body_lines)

    try:
        submission = subreddit.submit(title, selftext=body, flair_id=FLAIR_ID)
        try:
            submission.mod.distinguish(sticky=True)
        except:
            pass
        print(f"✅ Posted: {title}")
        save_posted(match["url"])
    except Exception as e:
        print(f"❌ Reddit post failed: {e}")

# ---------------- MAIN ----------------
def main(force_post=False):
    match = find_next_match()
    if not match:
        print("No upcoming unposted Munster match found.")
        return
    if already_posted(match["url"]):
        print("Already posted this match.")
        return
    now_utc = datetime.now(pytz.utc)
    post_time = match["datetime"] - timedelta(hours=POST_BEFORE_HOURS) if match["datetime"] else now_utc
    if force_post or now_utc >= post_time:
        post_match_thread(match)
    else:
        print(f"⏳ Not time yet. Scheduled post time: {post_time}")

if __name__ == "__main__":
    import sys
    force = "--force" in sys.argv or os.getenv("FORCE_POST") == "1"
    main(force_post=force)
