import praw
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import os
import json
import re
import pytz

# Configuration
TEAM_NAME = "Munster"
SUBREDDIT = "Munsterrugby"
MATCH_HISTORY_FILE = "posted.json"
TIMEZONE = pytz.timezone("Europe/Dublin")
FLAIR_ID = "44ddc6a8-a2a2-11f0-ab19-0257fc8eb3f2"

def load_posted():
    if not os.path.exists(MATCH_HISTORY_FILE):
        return []
    with open(MATCH_HISTORY_FILE, "r") as f:
        try:
            return json.load(f)
        except:
            return []

def save_posted(data):
    with open(MATCH_HISTORY_FILE, "w") as f:
        json.dump(data, f)

def fetch_match_page(url):
    """Fetch and parse the match-specific page, if available."""
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        return BeautifulSoup(r.text, "html.parser")
    except Exception:
        return None

def parse_starting_xv_from_gamepage(soup):
    """Given a match page soup, extract Munster and opponent starting XV lists."""
    # On the game page, there is a section "Match Day Squad" with two columns: Munster # Edinburgh
    table = soup.find(text=re.compile("Match Day Squad", re.I))
    if not table:
        return None, None
    parent = table.find_parent()
    if not parent:
        return None, None
    # Often the table rows have lines like "Munster # Edinburgh", then names in two columns
    rows = parent.find_all("tr")
    home = []
    away = []
    for row in rows:
        cols = row.find_all(["td","th"])
        if len(cols) >= 3:
            # e.g. MunsterName, “#”, EdinburghName
            h = cols[0].get_text(strip=True)
            a = cols[2].get_text(strip=True)
            home.append(h)
            away.append(a)
    if home and away:
        return home, away
    return None, None

def get_upcoming_matches():
    """Scrape rugbykickoff team page for fixtures."""
    team_url = f"https://rugbykickoff.com/teams/{TEAM_NAME.lower()}/"
    try:
        r = requests.get(team_url, timeout=20)
        r.raise_for_status()
    except Exception as e:
        print("Error fetching team page:", e)
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    matches = []
    for a in soup.select("a[href*='/game/']"):
        href = a.get("href")
        full = href if href.startswith("http") else ("https://rugbykickoff.com" + href)
        # parse date/time from element text or sibling
        context = a.get_text(" ", strip=True)
        # use regex for date/time
        dm = re.search(r"(\d{1,2}\s\w{3}\s\d{4}).*(\d{1,2}:\d{2})", context)
        if not dm:
            # fallback: use page
            game_soup = fetch_match_page(full)
            if game_soup:
                # find "When's the game on?" section
                text = game_soup.get_text(" ", strip=True)
                dm2 = re.search(r"(\d{1,2}\s\w{3}\s\d{4}).*(\d{1,2}:\d{2})", text)
                if dm2:
                    dm = dm2
        if not dm:
            continue
        datepart = dm.group(1)
        timepart = dm.group(2)
        dt = None
        try:
            dt = datetime.strptime(f"{datepart} {timepart}", "%d %b %Y %H:%M")
            dt = TIMEZONE.localize(dt)
        except Exception as e:
            continue

        matches.append({
            "teams": context,
            "datetime": dt,
            "url": full
        })
    print("Found matches:", [m["teams"] for m in matches])
    return matches

def reddit_client():
    return praw.Reddit(
        client_id=os.getenv("REDDIT_CLIENT_ID"),
        client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
        username=os.getenv("REDDIT_USERNAME"),
        password=os.getenv("REDDIT_PASSWORD"),
        user_agent=os.getenv("USER_AGENT")
    )

def post_match(match):
    reddit = reddit_client()
    subreddit = reddit.subreddit(SUBREDDIT)

    local_dt = match["datetime"]
    title = f"Match Thread: {match['teams']} — {local_dt.strftime('%A %d %b %Y @ %H:%M')} (IST)"
    body = []
    body.append(f"🏟️ **Venue / Match Page:** [Link]({match['url']})")
    body.append(f"🗓️ **Kickoff:** {local_dt.strftime('%A %d %b %Y, %H:%M (IST)')}")
    body.append(f"**Teams:** {match['teams']}")
    body.append("")

    # Try fetch starting XV
    game_soup = fetch_match_page(match["url"])
    if game_soup:
        home, away = parse_starting_xv_from_gamepage(game_soup)
        if home and away:
            body.append("### 🏉 Starting XV")
            # build simple code block
            for i in range(min(len(home), len(away))):
                body.append(f"{home[i]} vs {away[i]}")
            body.append("")

    body.append("**Stand Up And Fight! 💪🔴**")
    body.append(f"*Posted by MunsterKickoff Bot 🤖*")

    full_body = "\n".join(body)
    submission = subreddit.submit(title, selftext=full_body)
    try:
        submission.flair.select(FLAIR_ID)
    except Exception as e:
        print("Could not select flair:", e)

    print("✅ Posted:", title)
    return submission.id

if __name__ == "__main__":
    matches = get_upcoming_matches()
    posted = load_posted()
    for m in matches:
        if m["teams"] in posted:
            continue
        # check time
        if m["datetime"] - datetime.now(TIMEZONE) <= timedelta(hours=4):
            sid = post_match(m)
            posted.append(m["teams"])
            save_posted(posted)
            break
