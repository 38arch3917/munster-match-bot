import os
import praw
import requests
from datetime import datetime, timedelta
import pytz
import re

# === CONFIG ===
SUBREDDIT = "MunsterRugby"
TEAM_NAME = "Munster"
POST_HOURS_BEFORE = 3
USER_AGENT = "script:munster_match_bot:v9 (by u/MunsterKickoff)"
SEASON_PAGE = "2025-26_Munster_Rugby_season"

# === REDDIT LOGIN ===
def reddit_login():
    reddit = praw.Reddit(
        client_id=os.getenv("REDDIT_CLIENT_ID"),
        client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
        username=os.getenv("REDDIT_USERNAME"),
        password=os.getenv("REDDIT_PASSWORD"),
        user_agent=os.getenv("USER_AGENT", USER_AGENT)
    )
    print(f"✅ Logged in as: {reddit.user.me()}")
    return reddit

# === GET RAW WIKITEXT ===
def get_wikitext(page):
    URL = "https://en.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "prop": "revisions",
        "titles": page,
        "rvprop": "content",
        "format": "json",
        "rvslots": "main"
    }
    headers = {"User-Agent": USER_AGENT}
    res = requests.get(URL, params=params, headers=headers)
    
    if res.status_code != 200:
        print(f"❌ Wikipedia API request failed with status code {res.status_code}")
        print(res.text[:500])  # debug first 500 chars
        return None
    
    try:
        data = res.json()
        page_data = next(iter(data["query"]["pages"].values()))
        return page_data["revisions"][0]["slots"]["main"]["*"]
    except Exception as e:
        print(f"❌ Failed to parse Wikipedia JSON: {e}")
        return None

# === PARSE RUGBYBOX FIXTURES ===
def parse_rugbybox_fixtures(wikitext):
    pattern = re.compile(
        r"\{\{rugbybox.*?\n"
        r"\| date\s*=\s*(.*?)\n"
        r"\| time\s*=\s*(.*?)\n"
        r"\| home\s*=\s*(.*?)\n.*?"
        r"\| away\s*=\s*(.*?)\n.*?"
        r"\| stadium\s*=\s*(.*?)\n",
        re.DOTALL
    )
    matches = re.findall(pattern, wikitext)
    fixtures = []
    for m in matches:
        date, time, home, away, stadium = m
        fixtures.append({
            "date": date.strip(),
            "time": time.strip(),
            "home": home.strip(),
            "away": away.strip(),
            "stadium": stadium.strip()
        })
    return fixtures

# === FIND NEXT FIXTURE ===
def get_next_fixture(fixtures):
    now = datetime.utcnow().replace(tzinfo=pytz.UTC)
    for fx in fixtures:
        dt_str = f"{fx['date']} {fx['time']}"
        try:
            parsed = datetime.strptime(dt_str, "%d %B %Y %H:%M")
            parsed = pytz.timezone("Europe/Dublin").localize(parsed).astimezone(pytz.UTC)
            if parsed > now:
                fx['kickoff_dt'] = parsed
                return fx
        except Exception:
            continue
    return None

# === FORMAT POST BODY ===
def format_post(fixture):
    kickoff = fixture.get("time") or "TBC"
    stadium = fixture.get("stadium") or "TBC"
    body = f"""**FULL TIME:** _(to be updated after match)_ 🏉

---

🏟️ **Venue:** {stadium}  
⏰ **Kickoff:** {fixture['date']}, {kickoff}  
🏆 **Competition:** United Rugby Championship  

---

**Match:** {fixture['home']} vs {fixture['away']}

---

*Automated by /u/MunsterKickoff 🤖*
"""
    return body

# === MAIN ===
def main():
    print("🚀 Munster Bot Starting...")

    reddit = reddit_login()
    wikitext = get_wikitext(SEASON_PAGE)
    if not wikitext:
        print("❌ Could not fetch Wikipedia wikitext.")
        return

    fixtures = parse_rugbybox_fixtures(wikitext)
    if not fixtures:
        print("❌ No fixtures found.")
        return

    print(f"Found {len(fixtures)} fixtures:")
    for f in fixtures:
        print(f)

    next_fixture = get_next_fixture(fixtures)
    if not next_fixture:
        print("✅ No upcoming fixtures found.")
        return

    print(f"🏉 Next Fixture: {next_fixture}")

    title = f"[Match Thread] {next_fixture['home']} vs {next_fixture['away']} ({datetime.utcnow().strftime('%a')})"
    body = format_post(next_fixture)

    subreddit = reddit.subreddit(SUBREDDIT)
    subreddit.submit(title, selftext=body)
    print("✅ Posted match thread successfully.")

if __name__ == "__main__":
    main()
