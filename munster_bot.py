import praw
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import pytz

# ============ CONFIG ============
SUBREDDIT = "MunsterRugby"
POST_BEFORE_HOURS = 3
TIMEZONE = pytz.timezone("Europe/Dublin")
# ================================

def reddit_login():
    print("🔐 Logging into Reddit...")
    reddit = praw.Reddit(
        client_id=os.getenv("CLIENT_ID"),
        client_secret=os.getenv("CLIENT_SECRET"),
        username=os.getenv("USERNAME"),
        password=os.getenv("PASSWORD"),
        user_agent=os.getenv("USER_AGENT"),
    )
    print(f"✅ Logged in as {reddit.user.me()}")
    return reddit

def infer_season_years():
    """Determine current and next season strings dynamically."""
    now = datetime.now()
    current_year = now.year
    next_year = now.year + 1
    # e.g. "2025–26", "2026–27"
    this_season = f"{current_year}–{str(next_year)[-2:]}"
    next_season = f"{next_year}–{str(next_year + 1)[-2:]}"
    return [this_season, next_season]

def discover_wikipedia_fixture_page():
    """Find the most relevant Munster Rugby season Wikipedia page."""
    print("🔍 Searching Wikipedia for latest Munster Rugby season...")
    seasons = infer_season_years()
    queries = [
        "Munster Rugby fixtures",
        "Munster Rugby season",
        f"Munster Rugby {seasons[0]} season",
        f"Munster Rugby {seasons[1]} season",
    ]
    for q in queries:
        url = f"https://en.wikipedia.org/w/index.php?search={q.replace(' ', '+')}"
        r = requests.get(url)
        soup = BeautifulSoup(r.text, "html.parser")
        link = soup.select_one(".mw-search-result-heading a")
        if link:
            page = "https://en.wikipedia.org" + link["href"]
            print(f"🧾 Found Wikipedia page: {page}")
            return page
    print("⚠️ No Wikipedia season page found.")
    return None

def parse_fixtures_from_page(url):
    """Extract fixture list from the season page."""
    print(f"📄 Parsing fixtures from: {url}")
    r = requests.get(url)
    soup = BeautifulSoup(r.text, "html.parser")
    tables = soup.find_all("table", {"class": "wikitable"})
    fixtures = []
    for table in tables:
        headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]
        if "opponent" in headers or "date" in headers:
            for row in table.find_all("tr")[1:]:
                cells = [td.get_text(" ", strip=True) for td in row.find_all("td")]
                if len(cells) >= 3:
                    fixtures.append(cells)
    return fixtures

def parse_datetime(date_text):
    """Attempt to parse date text into a datetime object."""
    for fmt in ("%d %B %Y", "%d %b %Y", "%A %d %B %Y"):
        try:
            return TIMEZONE.localize(datetime.strptime(date_text, fmt))
        except Exception:
            continue
    return None

def find_next_match(fixtures):
    """Find the next upcoming match from parsed fixture list."""
    now = datetime.now(TIMEZONE)
    for fixture in fixtures:
        date = parse_datetime(fixture[0])
        if date and date > now:
            return fixture
    return None

def create_post_title(fixture):
    """Generate Reddit post title."""
    opponent = fixture[1]
    competition = fixture[-1]
    date = fixture[0]
    return f"🏉 Munster vs {opponent} | {competition} | {date[:3]}"

def create_post_body(fixture):
    """Generate post body."""
    date = fixture[0]
    opponent = fixture[1]
    venue = fixture[2] if len(fixture) > 2 else "TBC"
    competition = fixture[-1]
    body = f"""
🏉 **Fixture:** Munster vs {opponent}
📅 **Date:** {date}
📍 **Venue:** {venue}
🏆 **Competition:** {competition}

🔥 **Standings:** [View on Wikipedia](https://en.wikipedia.org/wiki/United_Rugby_Championship)

---

_Automated by /u/MunsterKickoff 🤖_
"""
    return body.strip()

def post_thread(reddit, fixture):
    """Post the match thread on Reddit."""
    subreddit = reddit.subreddit(SUBREDDIT)
    title = create_post_title(fixture)
    body = create_post_body(fixture)
    print(f"📝 Posting thread: {title}")
    subreddit.submit(title=title, selftext=body)
    print("✅ Posted successfully!")

if __name__ == "__main__":
    import os
    print("🚀 Munster Rugby Match Thread Bot started...")
    reddit = reddit_login()
    page = discover_wikipedia_fixture_page()
    if not page:
        print("❌ Could not find a Wikipedia page. Exiting.")
        exit(0)
    fixtures = parse_fixtures_from_page(page)
    next_match = find_next_match(fixtures)
    if not next_match:
        print("🕐 No upcoming fixtures found.")
        exit(0)
    # Check if match is within 3 hours
    match_time = parse_datetime(next_match[0])
    now = datetime.now(TIMEZONE)
    if match_time and 0 < (match_time - now).total_seconds() <= POST_BEFORE_HOURS * 3600:
        post_thread(reddit, next_match)
    else:
        print("⏰ No match within 3 hours. Waiting...")
