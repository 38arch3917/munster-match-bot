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
# ------------------------------------------------

def to_ist(dt):
    """Convert UTC datetime to Irish Standard/Daylight Time."""
    return dt.replace(tzinfo=pytz.utc).astimezone(TIMEZONE)

def get_post_time(match):
    """Return the UTC datetime when the match thread should be posted (4 hours before kickoff)."""
    return match["datetime"] - timedelta(hours=4)

# ---------------- SCRAPING FUNCTIONS ----------------
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
            dt = dt.replace(tzinfo=pytz.utc)
        except ValueError:
            continue

        if dt < datetime.utcnow() - timedelta(days=1):
            continue

        teams_match = re.search(r"([A-Za-z\s]+)\s+vs\.?\s+([A-Za-z\s]+)", text)
        teams = teams_match.group(0).strip() if teams_match else TEAM_NAME
        competition = "URC" if "URC" in text else "Fixture"

        venue = "Unknown venue"
        venue_el = fixture.find(string=re.compile("Park|Stadium|Ground", re.I))
        if venue_el:
            venue = venue_el.strip()

        matches.append({
            "teams": teams,
            "datetime": dt,
            "url": TEAM_URL,
            "competition": competition,
            "venue": venue
        })

    print(f"Found {len(matches)} future matches.")
    return matches

def get_today_match(matches):
    now = datetime.utcnow().replace(tzinfo=pytz.utc)
    for match in matches:
        if 0 <= (match["datetime"] - now).total_seconds() < 86400:
            return match
    return None

# ---------------- REDDIT FUNCTIONS ----------------
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

# ---------------- POST BUILDING ----------------
def format_post_body(match):
    dt_ist = to_ist(match["datetime"])
    kickoff_str = dt_ist.strftime("%A %d %b %Y @ %H:%Mhrs (IST)")
    venue = match["venue"]
    comp = match["competition"]

    body = f"""
🏟️ **{venue}**  
🗓️ **{kickoff_str}** – **{comp}**

🏉 **Starting XV** 🏉  
| # | Munster | Position | Opponent |
|:-:|:-:|:-:|:-:|
| 1 | Loughman | LH Prop | Andrews |
| 2 | Barron | Hooker | Dacey |
| 3 | Ryan | TH Prop | Arhip |
| 4 | Beirne | Lock | Seb Davies |
| 5 | Kleyn | Lock | Hill |
| 6 | Coombes | Flanker | Turnbull |
| 7 | Hodnett | Flanker | Jenkins |
| 8 | O’Mahony (C) | No.8 | Botham |

📊 **URC Standings (Example)**  
| Pos | Team | P | W | D | L | PF | PA | PD | Pts |
|:--:|:--|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| 1 | Leinster | 4 | 4 | 0 | 0 | 132 | 67 | +65 | 20 |
| 2 | **Munster 🔴** | 4 | 3 | 0 | 1 | 110 | 82 | +28 | 15 |
| 4 | **Cardiff 🔵** | 4 | 2 | 1 | 1 | 97 | 93 | +4 | 13 |

📈 **Recent Form**  
Munster: 🟢 🟢 🟡 🟢 🔴  
Cardiff: 🔴 🟢 🔴 🟡 🔴  

⚖️ **Officials**  
Referee: Andrew Brace  
Assistant Referees: Frank Murphy, Chris Busby  
TMO: Brian MacNeice  

📺 **Broadcasters:** RTÉ 2, Premier Sports  

💬 **Discuss below!**  
How do you rate Munster’s lineup tonight? Predictions welcome ⬇️  

**Stand Up And Fight! 💪🔴**  

*Posted by MunsterKickoff 🤖 – created by /u/i93*
"""
    return body.strip()

# ---------------- POSTING ----------------
def post_match_thread(match):
    reddit = reddit_client()
    subreddit = reddit.subreddit(SUBREDDIT)
    dt_ist = to_ist(match["datetime"])
    title = f"Match Thread: {match['teams']} – {match['competition']} ({dt_ist.strftime('%A %d %b %Y @ %H:%Mhrs (IST)')})"
    body = format_post_body(match)

    flair_id = "44ddc6a8-a2a2-11f0-ab19-0257fc8eb3f2"
    submission = subreddit.submit(title, selftext=body, flair_id=flair_id)
    print(f"✅ Posted: {title}")
    print(f"URL: {submission.url}")

# ---------------- MAIN LOGIC ----------------
if __name__ == "__main__":
    matches = get_munster_matches()
    if not matches:
        print("No matches found.")
        exit()

    today_match = get_today_match(matches)
    if today_match:
        post_time = get_post_time(today_match)
        now = datetime.utcnow().replace(tzinfo=pytz.utc)
        if now >= post_time and not already_posted(today_match):
            post_match_thread(today_match)
            save_posted(today_match)
        else:
            print(f"Match thread not posted yet. Scheduled for: {post_time} UTC")
    else:
        print("No Munster match today or already posted.")
