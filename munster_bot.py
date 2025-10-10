# munster_bot.py
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
RUGBYKICKOFF_FIXTURES = "https://www.rugbykickoff.com/Munster"
BROADCASTERS_WHITELIST = ["Premier Sports", "TG4", "RTÉ 2", "Access Munster", "URC.tv"]
# ---------------------------------------

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

def parse_datetime(date_str, time_str):
    try:
        # Example format: "Sat 25 Oct 2025" + "20:45 IST"
        dt = datetime.strptime(f"{date_str} {time_str}", "%a %d %b %Y %H:%M %Z")
        dt = IST.localize(dt)
        return dt
    except Exception:
        return None

def find_next_match():
    html = safe_get(RUGBYKICKOFF_FIXTURES)
    if not html:
        return None

    soup = BeautifulSoup(html, "html.parser")
    # Look for fixture cards
    fixtures = soup.select("a[href*='/game/']")
    for f in fixtures:
        href = f.get("href")
        if not href:
            continue
        full_url = href if href.startswith("http") else "https://www.rugbykickoff.com" + href

        if already_posted(full_url):
            continue

        # Extract opponent
        text = f.get_text(" ", strip=True)
        opponent_match = re.search(r"Munster\s+vs\.?\s+(.*)", text, re.I)
        opponent = opponent_match.group(1) if opponent_match else "Opponent"

        # Extract competition
        competition = "URC"
        comp_match = re.search(r"(United Rugby Championship|Champions Cup|Challenge Cup|Friendly|International)", text, re.I)
        if comp_match:
            competition = comp_match.group(1)

        # Extract date and time
        date_match = re.search(r"([A-Za-z]{3} \d{1,2} [A-Za-z]{3,9} \d{4})", text)
        time_match = re.search(r"(\d{1,2}:\d{2})", text)
        date_str = date_match.group(1) if date_match else None
        time_str = time_match.group(1) if time_match else None
        kickoff_dt = parse_datetime(date_str, time_str) if date_str and time_str else None

        # Extract venue
        venue = "TBC"
        venue_match = re.search(r"at\s+([A-Za-z0-9\s\.\-]+)", text)
        if venue_match:
            venue = venue_match.group(1)

        # Only return match if essential data exists
        if opponent and kickoff_dt and venue:
            return {
                "url": full_url,
                "home": "Munster",
                "away": opponent,
                "datetime": kickoff_dt,
                "venue": venue,
                "competition": competition,
                "broadcasters": BROADCASTERS_WHITELIST,
            }
    return None

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

    dt_ist = match["datetime"].astimezone(IST)
    date_str = dt_ist.strftime("%a %d %b %Y")
    time_str = dt_ist.strftime("%H:%M")

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

def main(force_post=False):
    match = find_next_match()
    if not match:
        print("No upcoming unposted Munster match found with complete data.")
        return
    if already_posted(match["url"]):
        print("Already posted this match.")
        return

    now_utc = datetime.now(pytz.utc)
    post_time = match["datetime"] - timedelta(hours=POST_BEFORE_HOURS)
    if force_post or now_utc >= post_time:
        post_match_thread(match)
    else:
        print(f"⏳ Not time yet. Scheduled post time: {post_time}")

if __name__ == "__main__":
    import sys
    force = "--force" in sys.argv or os.getenv("FORCE_POST") == "1"
    main(force_post=force)
