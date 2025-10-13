import praw
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import pytz
import re
import time

# === CONFIG ===
SUBREDDIT = "MunsterRugby"
TEAM_NAME = "Munster"
POST_HOURS_BEFORE = 3

WIKIPEDIA_BASE = "https://en.wikipedia.org/wiki/"
WIKIPEDIA_MAIN_PAGE = "Munster_Rugby"
USER_AGENT = "script:munster_match_bot:v3 (by u/MunsterKickoff)"

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

# === GET CURRENT SEASON PAGE ===
def get_current_season_url():
    res = requests.get(WIKIPEDIA_BASE + WIKIPEDIA_MAIN_PAGE)
    soup = BeautifulSoup(res.text, "html.parser")
    year = datetime.now().year
    links = soup.select("a[href*='Munster_Rugby_']")
    for link in links:
        href = link.get("href", "")
        if str(year) in href or str(year + 1) in href:
            return "https://en.wikipedia.org" + href
    return None

# === PARSE FIXTURES ===
def parse_fixtures(url):
    res = requests.get(url)
    soup = BeautifulSoup(res.text, "html.parser")

    tables = soup.find_all("table", {"class": "wikitable"})
    fixtures = []
    for table in tables:
        headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]
        if any(h in headers for h in ["opponent", "fixture", "opposition"]):
            for row in table.find_all("tr")[1:]:
                cols = [td.get_text(" ", strip=True) for td in row.find_all(["td", "th"])]
                if len(cols) < 3:
                    continue

                data = dict(zip(headers, cols))
                date = data.get("date") or data.get("day") or ""
                opponent = data.get("opponent") or data.get("opposition") or data.get("fixture") or ""
                venue = data.get("venue") or data.get("stadium") or ""
                competition = data.get("competition") or ""

                # Extract kickoff time if listed
                kickoff_time = None
                match = re.search(r"(\d{1,2}:\d{2})", " ".join(cols))
                if match:
                    kickoff_time = match.group(1)

                fixtures.append({
                    "date": date,
                    "opponent": opponent,
                    "venue": venue,
                    "competition": competition,
                    "kickoff_time": kickoff_time
                })
    return fixtures

# === PARSE STANDINGS (URC or Europe) ===
def parse_standings(soup):
    standings = []
    tables = soup.find_all("table", {"class": "wikitable"})
    for table in tables:
        header_text = table.find_previous("h3") or table.find_previous("h2")
        if header_text and any(x in header_text.get_text() for x in ["URC", "United Rugby Championship", "European Rugby Champions Cup"]):
            rows = table.find_all("tr")[1:]
            for row in rows:
                cols = [c.get_text(" ", strip=True) for c in row.find_all("td")]
                if len(cols) >= 2:
                    standings.append(cols[:5])
            break
    return standings

# === FORMAT STANDINGS TEXT ===
def format_standings_table(standings):
    if not standings:
        return ""
    text = "\n\n**Current Standings:**\n\n| Pos | Team | Pld | W | Pts |\n|:-:|:-|:-:|:-:|:-:|\n"
    for row in standings:
        text += f"| {' | '.join(row)} |\n"
    return text

# === FORMAT POST BODY ===
def format_post(fixture, standings_text):
    date = fixture['date']
    opponent = fixture['opponent']
    venue = fixture['venue']
    competition = fixture['competition']
    kickoff = fixture['kickoff_time'] or "TBC"

    body = f"""**FULL TIME:** _(to be updated after match)_ 🏉

---

🏟️ **Venue:** {venue or 'TBC'}  
🏆 **Competition:** {competition or 'TBC'}  
⏰ **Kickoff:** {date}, {kickoff}

---

{standings_text}

---

*Automated by /u/MunsterKickoff 🤖*
"""
    return body

# === FIND NEXT FIXTURE ===
def get_next_fixture(fixtures):
    now = datetime.now(pytz.UTC)
    for fx in fixtures:
        try:
            date_text = fx['date']
            parsed = datetime.strptime(date_text.split()[0], "%d %B %Y")
            if parsed.replace(tzinfo=pytz.UTC) > now:
                return fx
        except Exception:
            continue
    return None

# === MAIN ===
def main():
    print("🚀 Munster Bot Starting...")

    reddit = reddit_login()
    url = get_current_season_url()
    if not url:
        print("❌ Could not find current season Wikipedia page.")
        return

    print(f"📄 Using season page: {url}")
    fixtures = parse_fixtures(url)
    if not fixtures:
        print("❌ No fixtures found.")
        return

    next_fixture = get_next_fixture(fixtures)
    if not next_fixture:
        print("✅ No upcoming fixtures found.")
        return

    print(f"🏉 Next Fixture: {next_fixture}")

    # Fetch standings
    res = requests.get(url)
    soup = BeautifulSoup(res.text, "html.parser")
    standings = parse_standings(soup)
    standings_text = format_standings_table(standings)

    # Format post
    short_day = datetime.now().strftime("%a")
    title = f"[Match Thread] {TEAM_NAME} vs {next_fixture['opponent']} ({short_day})"
    body = format_post(next_fixture, standings_text)

    # Determine post time
    kickoff = next_fixture["kickoff_time"]
    kickoff_dt = datetime.now(pytz.UTC) + timedelta(hours=POST_HOURS_BEFORE)
    post_time = kickoff_dt - timedelta(hours=POST_HOURS_BEFORE)
    print(f"⏳ Scheduled to post 3 hours before kickoff ({post_time})")

    subreddit = reddit.subreddit(SUBREDDIT)
    subreddit.submit(title, selftext=body)
    print("✅ Posted match thread successfully.")

if __name__ == "__main__":
    import os
    main()
