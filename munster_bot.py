import os
import json
import requests
from datetime import datetime, timedelta
import pytz
from bs4 import BeautifulSoup
import praw

# ---------------- CONFIG ----------------
TEAM_NAME = "Munster"
SUBREDDIT = "Munsterrugby"
MATCH_HISTORY_FILE = "posted.json"
POST_BEFORE_HOURS = 4
FLAIR_ID = "44ddc6a8-a2a2-11f0-ab19-0257fc8eb3f2"
HEADERS = {"User-Agent": "Mozilla/5.0"}
IST = pytz.timezone("Europe/Dublin")
RUGBYPASS_FIXTURES = "https://www.rugbypass.com/teams/munster/fixtures-results/"
URC_FIXTURES = "https://www.unitedrugby.com/clubs/munster"
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

def parse_datetime(line):
    try:
        line = line.replace("st","").replace("nd","").replace("rd","").replace("th","")
        dt = datetime.strptime(line.strip(), "%a %d %B %Y, %H:%M %Z")
        dt = IST.localize(dt)
        return dt
    except:
        return None

def find_next_match():
    for url in [RUGBYPASS_FIXTURES, URC_FIXTURES]:
        html = safe_get(url)
        if not html:
            continue
        soup = BeautifulSoup(html, "html.parser")
        anchors = soup.find_all("a", href=True)
        for a in anchors:
            href = a["href"]
            if TEAM_NAME.lower() not in a.get_text(" ", strip=True).lower():
                continue
            full_url = href if href.startswith("http") else "https://www.rugbypass.com" + href
            if already_posted(full_url):
                continue
            parent_text = a.get_text(" ", strip=True)
            dt = None
            venue = None
            competition = None
            sibling = a.find_parent()
            if sibling:
                text = sibling.get_text(" ", strip=True)
                import re
                m = re.search(r'\b\d{1,2}\s+[A-Za-z]+\s+\d{4},\s*\d{1,2}:\d{2}\s*[A-Za-z]{2,3}\b', text)
                if m:
                    dt = parse_datetime(m.group(0))
                for v in ["Park", "Stadium", "Arena", "Ground", "St."]:
                    if v in text:
                        venue = text
                        break
                for c in ["URC", "United Rugby", "Champions Cup"]:
                    if c.lower() in text.lower():
                        competition = c
                        break
            return {
                "url": full_url,
                "home": "Munster",
                "away": "Opponent",
                "datetime": dt,
                "venue": venue or "TBC",
                "competition": competition or "URC",
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

    dt_ist = match["datetime"].astimezone(IST) if match["datetime"] else None
    date_str = dt_ist.strftime("%a %dth %b %Y") if dt_ist else "TBC"
    time_str = dt_ist.strftime("%H:%M") if dt_ist else "TBC"

    title = f"Match Thread: {match['home']} vs {match['away']} ({match['competition']}) - {date_str} {time_str} - {match['venue']}"

    body_lines = [
        f"🕒 **Kickoff:** {time_str} IST",
        f"📍 **Venue:** {match['venue']}",
        f"🏆 **Competition:** {match['competition']}",
        f"📺 **Broadcasters:** {', '.join(match['broadcasters'])}",
        "🏉 **Starting XV:**\n> Will be announced 1–2 days before kickoff.",
        "\n**Stand Up And Fight! 💪🔴**",
        "\n*Automated by /u/MunsterKickoff*"
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
