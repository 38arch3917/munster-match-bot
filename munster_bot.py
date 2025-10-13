import os
import praw
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import pytz

# === CONFIG ===
SUBREDDIT = "MunsterRugby"
TEAM_NAME = "Munster"
POST_HOURS_BEFORE = 3
USER_AGENT = "script:munster_match_bot:v11 (by u/MunsterKickoff)"
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

# === FETCH MATCHES SECTION HTML VIA WIKIPEDIA API ===
def fetch_matches_section_html(page_title):
    URL = "https://en.wikipedia.org/w/api.php"
    headers = {"User-Agent": USER_AGENT}

    # Step 1: Get sections
    params_sections = {
        "action": "parse",
        "page": page_title,
        "prop": "sections",
        "format": "json"
    }
    res = requests.get(URL, params=params_sections, headers=headers)
    if res.status_code != 200:
        print(f"❌ Failed to get sections: {res.status_code}")
        return None
    data = res.json()
    sections = data["parse"]["sections"]

    # Find the "Matches" section
    matches_section_index = None
    for s in sections:
        if "Matches" in s["line"]:
            matches_section_index = s["index"]
            break

    if not matches_section_index:
        print("❌ Could not find 'Matches' section.")
        return None

    # Step 2: Fetch HTML for that section
    params_section = {
        "action": "parse",
        "page": page_title,
        "prop": "text",
        "section": matches_section_index,
        "format": "json"
    }
    res2 = requests.get(URL, params=params_section, headers=headers)
    if res2.status_code != 200:
        print(f"❌ Failed to fetch section HTML: {res2.status_code}")
        return None

    section_html = res2.json()["parse"]["text"]["*"]
    return section_html

# === PARSE FIXTURES FROM RENDERED HTML ===
def parse_fixtures_from_html(section_html):
    soup = BeautifulSoup(section_html, "html.parser")
    fixtures = []

    # Rugbybox elements
    for rb in soup.select("div.rugbybox"):
        date = rb.find("div", class_="rb-date").get_text(strip=True) if rb.find("div", class_="rb-date") else ""
        time = rb.find("div", class_="rb-time").get_text(strip=True) if rb.find("div", class_="rb-time") else ""
        home = rb.find("div", class_="rb-home").get_text(strip=True) if rb.find("div", class_="rb-home") else ""
        away = rb.find("div", class_="rb-away").get_text(strip=True) if rb.find("div", class_="rb-away") else ""
        stadium = rb.find("div", class_="rb-stadium").get_text(strip=True) if rb.find("div", class_="rb-stadium") else ""

        fixtures.append({
            "date": date,
            "time": time,
            "home": home,
            "away": away,
            "stadium": stadium
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
    section_html = fetch_matches_section_html(SEASON_PAGE)
    if not section_html:
        print("❌ Could not fetch Matches section HTML.")
        return

    fixtures = parse_fixtures_from_html(section_html)
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
