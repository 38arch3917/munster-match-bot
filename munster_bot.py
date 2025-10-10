import praw
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import pytz
import os
import json

TEAM_NAME = "Munster"
SUBREDDIT = "Munsterrugby"
MATCH_HISTORY_FILE = "posted.json"
BASE_URL = "https://www.rugbypass.com/live/"
FLAIR_ID = "44ddc6a8-a2a2-11f0-ab19-0257fc8eb3f2"

IST = pytz.timezone("Europe/Dublin")

def get_next_munster_match():
    print("Fetching next Munster match from RugbyPass...")
    try:
        r = requests.get("https://www.rugbypass.com/fixtures/munster/", timeout=20)
        r.raise_for_status()
    except Exception as e:
        print(f"❌ Error fetching fixtures: {e}")
        return None

    soup = BeautifulSoup(r.text, "html.parser")
    link = soup.select_one('a[href*="/live/munster-vs"], a[href*="/live/vs-munster"]')
    if not link:
        print("❌ No upcoming Munster matches found.")
        return None

    match_url = "https://www.rugbypass.com" + link["href"]
    return scrape_match_details(match_url)

def scrape_match_details(url):
    print(f"Scraping match details from {url}")
    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
    except Exception as e:
        print(f"❌ Error fetching match page: {e}")
        return None

    soup = BeautifulSoup(r.text, "html.parser")

    # Title
    title_el = soup.select_one("h1")
    title = title_el.get_text(strip=True) if title_el else "Munster Match"

    # Date, time, and venue
    meta = soup.select_one(".match-details")
    meta_text = meta.get_text(" ", strip=True) if meta else ""
    date_time = soup.select_one(".fixture__date")
    kickoff_str = date_time.get_text(strip=True) if date_time else ""
    venue = soup.select_one(".fixture__venue")
    venue_text = venue.get_text(strip=True) if venue else "TBC"

    # Parse kickoff time (if available)
    dt = datetime.utcnow() + timedelta(days=1)
    for fmt in ("%A %d %B %Y %H:%M", "%d %B %Y %H:%M"):
        try:
            dt = datetime.strptime(kickoff_str, fmt)
            break
        except Exception:
            continue
    dt_ist = IST.localize(dt)
    dt_utc = dt_ist.astimezone(pytz.utc)

    # Competition
    comp_el = soup.select_one(".fixture__competition")
    competition = comp_el.get_text(strip=True) if comp_el else "Fixture"

    # Broadcasters
    broadcasters = []
    for b in soup.select(".fixture__broadcasters img"):
        broadcasters.append(b.get("alt", "Broadcaster"))

    # Lineups
    home_team = soup.select_one(".team--home .team__name").get_text(strip=True)
    away_team = soup.select_one(".team--away .team__name").get_text(strip=True)

    lineups = {}
    for side, key in [("home", home_team), ("away", away_team)]:
        players = []
        for p in soup.select(f".team--{side} .player__name"):
            players.append(p.get_text(strip=True))
        lineups[key] = players

    return {
        "url": url,
        "teams": f"{home_team} vs. {away_team}",
        "competition": competition,
        "venue": venue_text,
        "datetime": dt_utc,
        "broadcasters": broadcasters,
        "lineups": lineups
    }

def reddit_client():
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
    with open(MATCH_HISTORY_FILE) as f:
        data = json.load(f)
    return match["url"] in data

def save_posted(match):
    data = []
    if os.path.exists(MATCH_HISTORY_FILE):
        with open(MATCH_HISTORY_FILE) as f:
            data = json.load(f)
    data.append(match["url"])
    with open(MATCH_HISTORY_FILE, "w") as f:
        json.dump(data, f)

def post_match_thread(match):
    reddit = reddit_client()
    subreddit = reddit.subreddit(SUBREDDIT)

    dt_ist = match["datetime"].astimezone(IST)
    title = (
        f"Match Thread: {match['teams']} "
        f"({match['competition']}) - "
        f"{dt_ist.strftime('%A %d %b %Y @ %H:%M')} (IST) - {match['venue']}"
    )

    # Build body
    body = f"🏉 **Kickoff:** {dt_ist.strftime('%A %d %B %Y @ %H:%M (IST)')}\n\n"
    body += f"📍 **Venue:** {match['venue']}\n\n"
    body += f"🏆 **Competition:** {match['competition']}\n\n"
    if match["broadcasters"]:
        body += "📺 **Broadcasters:** " + ", ".join(match["broadcasters"]) + "\n\n"

    # Starting XV
    home, away = match["teams"].split(" vs. ")
    home_players = match["lineups"].get(home, [])
    away_players = match["lineups"].get(away, [])
    body += f"🏉 **Starting XV:**\n\n| # | {home} | {away} |\n|:--:|:--:|:--:|\n"
    for i in range(15):
        h = home_players[i] if i < len(home_players) else ""
        a = away_players[i] if i < len(away_players) else ""
        body += f"| {i+1} | {h} | {a} |\n"
    body += "\n**Stand Up And Fight! 💪🔴**\n\n"
    body += f"---\n_MunsterKickoff Bot created by /u/i93_"

    submission = subreddit.submit(title, selftext=body, flair_id=FLAIR_ID)
    print(f"✅ Posted: {title}")
    save_posted(match)

def main():
    match = get_next_munster_match()
    if not match:
        print("❌ No upcoming match found.")
        return

    now = datetime.utcnow().replace(tzinfo=pytz.utc)
    post_time = match["datetime"] - timedelta(hours=4)
    if now >= post_time and not already_posted(match):
        post_match_thread(match)
    else:
        print(f"⏳ Not time yet. Kickoff: {match['datetime']} | Post time: {post_time}")

if __name__ == "__main__":
    main()
