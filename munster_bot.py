import os
import praw
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import pytz
import re

# === CONFIG ===
SUBREDDIT = "MunsterRugby"
TEAM_NAME = "Munster"
POST_HOURS_BEFORE = 3

WIKIPEDIA_BASE = "https://en.wikipedia.org/wiki/"
WIKIPEDIA_MAIN_PAGE = "Munster_Rugby"
USER_AGENT = "script:munster_match_bot:v7 (by u/MunsterKickoff)"

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
    headers = {"User-Agent": USER_AGENT}
    res = requests.get(WIKIPEDIA_BASE + WIKIPEDIA_MAIN_PAGE, headers=headers)
    soup = BeautifulSoup(res.text, "html.parser")
    year = datetime.utcnow().year

    links = soup.select("a[href*='Munster_Rugby_']")
    for link in links:
        href = link.get("href", "")
        if re.search(rf"{year}–\d{{2}}", href) or str(year) in href or str(year+1) in href:
            return "https://en.wikipedia.org" + href
    return None

# === PARSE FIXTURES (ROBUST) ===
def parse_fixtures(url):
    headers = {"User-Agent": USER_AGENT}
    res = requests.get(url, headers=headers)
    soup = BeautifulSoup(res.text, "html.parser")

    tables = soup.find_all("table", {"class": "wikitable"})
    fixtures = []

    for table in tables:
        headers_row = [th.get_text(strip=True).lower() for th in table.find_all("th")]

        # Relaxed detection of fixture tables
        if any(re.search(r"opponent|fixture|opposition|team|vs|date|time", h) for h in headers_row):
            for row in table.find_all("tr")[1:]:
                cols = [td.get_text(" ", strip=True) for td in row.find_all(["td", "th"])]
                if len(cols) < 2:
                    continue

                data = dict(zip(headers_row, cols))

                # Extract date
                date = data.get("date") or cols[0]

                # Extract opponent / fixture name
                opponent = (
                    data.get("opponent")
                    or data.get("opposition")
                    or data.get("fixture")
                    or data.get("team")
                    or (cols[1] if len(cols) > 1 else "")
                )

                # Venue / Competition
                venue = data.get("venue") or data.get("stadium") or ""
                competition = data.get("competition") or ""

                # Kickoff time: header or regex fallback
                kickoff_time = data.get("kickoff") or data.get("time")
                if not kickoff_time:
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

# === PARSE STANDINGS ===
def parse_standings(soup):
    standings = []
    tables = soup.find_all("table", {"class": "wikitable"})
    for table in tables:
        header_text = table.find_previous(["h2", "h3"])
        if header_text and any(x in header_text.get_text() for x in ["URC", "United Rugby Championship", "European Rugby Champions Cup"]):
            rows = table.find_all("tr")[1:]
            for row in rows:
                cols = [c.get_text(" ", strip=True) for c in row.find_all("td")]
                if len(cols) >= 5:
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
    now = datetime.utcnow().replace(tzinfo=pytz.UTC)
    for fx in fixtures:
        # Take only day, month, year for date parsing
        date_parts = fx['date'].strip().split()[0:3]
        date_str = " ".join(date_parts)
        time_str = fx.get("kickoff_time") or "00:00"
        dt_str = f"{date_str} {time_str}"

        try:
            parsed = datetime.strptime(dt_str, "%d %B %Y %H:%M").replace(tzinfo=pytz.UTC)
            if parsed > now:
                return fx
        except Exception:
            # fallback to date-only parsing
            try:
                parsed = datetime.strptime(date_str, "%d %B %Y").replace(tzinfo=pytz.UTC)
                if parsed > now:
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

    # Debug: print all parsed fixtures
    print(f"Found {len(fixtures)} fixtures:")
    for f in fixtures:
        print(f)

    next_fixture = get_next_fixture(fixtures)
    if not next_fixture:
        print("✅ No upcoming fixtures found.")
        return

    print(f"🏉 Next Fixture: {next_fixture}")

    # Fetch standings
    headers = {"User-Agent": USER_AGENT}
    res = requests.get(url, headers=headers)
    soup = BeautifulSoup(res.text, "html.parser")
    standings = parse_standings(soup)
    standings_text = format_standings_table(standings)

    # Format post
    short_day = datetime.utcnow().strftime("%a")
    title = f"[Match Thread] {TEAM_NAME} vs {next_fixture['opponent']} ({short_day})"
    body = format_post(next_fixture, standings_text)

    subreddit = reddit.subreddit(SUBREDDIT)
    subreddit.submit(title, selftext=body)
    print("✅ Posted match thread successfully.")

if __name__ == "__main__":
    main()
