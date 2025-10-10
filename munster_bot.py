import praw
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import pytz
import os
import json
import re

TEAM_NAME = "Munster"
SUBREDDIT = "Munsterrugby"
MATCH_HISTORY_FILE = "posted.json"
FIXTURES_URL = "https://www.rugbypass.com/teams/munster/fixtures-results/"
FLAIR_ID = "44ddc6a8-a2a2-11f0-ab19-0257fc8eb3f2"

IST = pytz.timezone("Europe/Dublin")


def get_next_munster_match():
    print("🔎 Fetching Munster fixtures from RugbyPass...")
    try:
        r = requests.get(FIXTURES_URL, timeout=20)
        r.raise_for_status()
    except Exception as e:
        print(f"❌ Error fetching fixtures page: {e}")
        return None

    soup = BeautifulSoup(r.text, "html.parser")
    matches = soup.select("a[href*='/live/']")

    for a in matches:
        link = a["href"]
        if "munster" not in link.lower():
            continue

        # ✅ Fix: handle full vs relative URLs
        if link.startswith("http"):
            full_url = link.split("?")[0]
        else:
            full_url = "https://www.rugbypass.com" + link.split("?")[0]

        if not already_posted_url(full_url):
            print(f"✅ Next match found: {full_url}")
            return scrape_match_details(full_url)

    print("❌ No new Munster matches found.")
    return None


def scrape_match_details(url):
    print(f"⚙️ Scraping match details from {url}")
    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
    except Exception as e:
        print(f"❌ Error fetching match page: {e}")
        return None

    soup = BeautifulSoup(r.text, "html.parser")

    # Teams
    home_team = soup.select_one(".fixture__team--home .fixture__team-name")
    away_team = soup.select_one(".fixture__team--away .fixture__team-name")
    home = home_team.get_text(strip=True) if home_team else "Home"
    away = away_team.get_text(strip=True) if away_team else "Away"

    # Competition and venue
    comp = soup.select_one(".fixture__competition-name")
    competition = comp.get_text(strip=True) if comp else "Fixture"
    venue = soup.select_one(".fixture__venue")
    venue_text = venue.get_text(strip=True) if venue else "TBC"

    # Kickoff time
    kickoff_str = ""
    date_el = soup.select_one(".fixture__date")
    if date_el:
        kickoff_str = date_el.get_text(strip=True)

    dt = None
    if kickoff_str:
        # Try to extract a proper datetime
        for fmt in ("%A %d %B %Y %H:%M", "%d %B %Y %H:%M", "%A %d %B %Y", "%d %B %Y"):
            try:
                dt = datetime.strptime(kickoff_str, fmt)
                dt = IST.localize(dt)
                break
            except Exception:
                continue

    # ✅ Fix: Handle live or missing times
    now = datetime.now(IST)
    live_tag = soup.select_one(".live-label, .fixture-status--live")
    if not dt or (dt.date() == now.date() and dt < now):
        print("📺 Match appears to be LIVE or missing kickoff time — posting immediately.")
        dt = now  # treat as current time

    dt_utc = dt.astimezone(pytz.utc)

    # Broadcasters
    broadcasters = [img.get("alt", "Broadcaster") for img in soup.select(".fixture__broadcasters img")]

    # Lineups
    lineups = {home: [], away: []}
    for side, team in [("home", home), ("away", away)]:
        for p in soup.select(f".team--{side} .player__name"):
            lineups[team].append(p.get_text(strip=True))

    return {
        "url": url,
        "teams": f"{home} vs. {away}",
        "competition": competition,
        "venue": venue_text,
        "datetime": dt_utc,
        "broadcasters": broadcasters,
        "lineups": lineups,
    }


def reddit_client():
    return praw.Reddit(
        client_id=os.getenv("REDDIT_CLIENT_ID"),
        client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
        username=os.getenv("REDDIT_USERNAME"),
        password=os.getenv("REDDIT_PASSWORD"),
        user_agent=os.getenv("USER_AGENT"),
    )


def already_posted_url(url):
    if not os.path.exists(MATCH_HISTORY_FILE):
        return False
    with open(MATCH_HISTORY_FILE) as f:
        data = json.load(f)
    return url in data


def save_posted_url(url):
    data = []
    if os.path.exists(MATCH_HISTORY_FILE):
        with open(MATCH_HISTORY_FILE) as f:
            data = json.load(f)
    data.append(url)
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

    body = f"🏉 **Kickoff:** {dt_ist.strftime('%A %d %B %Y @ %H:%M (IST)')}\n\n"
    body += f"📍 **Venue:** {match['venue']}\n\n"
    body += f"🏆 **Competition:** {match['competition']}\n\n"
    if match["broadcasters"]:
        body += "📺 **Broadcasters:** " + ", ".join(match["broadcasters"]) + "\n\n"

    home, away = match["teams"].split(" vs. ")
    home_players = match["lineups"].get(home, [])
    away_players = match["lineups"].get(away, [])
    body += f"🏉 **Starting XV:**\n\n| # | {home} | {away} |\n|:--:|:--:|:--:|\n"
    for i in range(15):
        h = home_players[i] if i < len(home_players) else ""
        a = away_players[i] if i < len(away_players) else ""
        body += f"| {i+1} | {h} | {a} |\n"

    body += "\n**Stand Up And Fight! 💪🔴**\n\n"
    body += f"---\n_Automated by /u/MunsterKickoff 🤖_"

    submission = subreddit.submit(title, selftext=body, flair_id=FLAIR_ID)
    print(f"✅ Posted: {title}")
    save_posted_url(match["url"])


def main():
    match = get_next_munster_match()
    if not match:
        print("❌ No match data found.")
        return

    now = datetime.utcnow().replace(tzinfo=pytz.utc)
    post_time = match["datetime"] - timedelta(hours=4)

    # ✅ Post if live or within posting window
    if now >= post_time or abs((now - match["datetime"]).total_seconds()) < 7200:
        post_match_thread(match)
    else:
        print(f"⏳ Not time yet. Kickoff: {match['datetime']} | Post time: {post_time}")


if __name__ == "__main__":
    main()
