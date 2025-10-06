# munster_bot.py
# Final MunsterKickoff poster
# Requirements: praw, requests, beautifulsoup4 (installed in workflow)

import praw
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import os
import json
import re
import sys
from typing import Tuple, Optional, List

# ---------------- CONFIGURATION ----------------
TEAM_NAME = "Munster"
SUBREDDIT = "Munsterrugby"
MATCH_HISTORY_FILE = "posted.json"
TEAM_URL = "https://rugbykickoff.com/teams/munster/"
IRELAND_TZ = ZoneInfo("Europe/Dublin")
FLAIR_ID = "44ddc6a8-a2a2-11f0-ab19-0257fc8eb3f2"  # Match Thread 🔴
# ------------------------------------------------

# Helper: safe load/save JSON
def load_posted() -> List[dict]:
    if not os.path.exists(MATCH_HISTORY_FILE):
        return []
    try:
        with open(MATCH_HISTORY_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return []

def save_posted_list(data: List[dict]):
    with open(MATCH_HISTORY_FILE, "w") as f:
        json.dump(data, f, default=str, indent=2)

def add_posted_entry(entry: dict):
    data = load_posted()
    data.append(entry)
    save_posted_list(data)

def update_posted_entry(submission_id: str, updates: dict):
    data = load_posted()
    changed = False
    for e in data:
        if e.get("submission_id") == submission_id:
            e.update(updates)
            changed = True
    if changed:
        save_posted_list(data)

# ------------ Time helpers ------------
def get_post_time(match):
    """Return the UTC datetime when the match thread should be posted (4 hours before kickoff)."""
    return match["datetime"] - timedelta(hours=4)

# ------------ Scraping fixtures ------------
def get_munster_matches():
    """Scrape rugbykickoff.com for Munster fixtures. Best-effort parsing."""
    print("Fetching Munster fixtures...")
    try:
        r = requests.get(TEAM_URL, timeout=20)
        r.raise_for_status()
    except Exception as e:
        print(f"Error fetching fixtures page: {e}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    matches = []

    # best-effort: find possible fixture list items
    fixture_candidates = soup.select(".fixture, .match, .upcoming-fixture, li") or soup.find_all("li")

    for fixture in fixture_candidates:
        text = fixture.get_text(" ", strip=True)
        if TEAM_NAME.lower() not in text.lower():
            continue

        # date/time pattern e.g. Fri 10 Oct 2025 19:00 or Fri 10 Oct 2025, 19:00
        date_match = re.search(r"(\w{3}\s\d{1,2}\s\w{3}\s\d{4})[,\s]*?(\d{1,2}:\d{2})?", text)
        if not date_match:
            continue
        date_str = f"{date_match.group(1)} {date_match.group(2) or '00:00'}"
        try:
            dt = datetime.strptime(date_str, "%a %d %b %Y %H:%M")
            dt = dt.replace(tzinfo=ZoneInfo("UTC"))
        except ValueError:
            # skip if we can't parse
            continue

        # ignore very old matches (safety)
        if dt < datetime.now(ZoneInfo("UTC")) - timedelta(days=2):
            continue

        # teams
        teams_match = re.search(r"([A-Za-z\.\'\-\s]+)\s+vs\.?\s+([A-Za-z\.\'\-\s]+)", text, re.I)
        if teams_match:
            teams = f"{teams_match.group(1).strip()} vs {teams_match.group(2).strip()}"
        else:
            # fallback: entire fixture text
            teams = TEAM_NAME

        # venue best-effort
        venue = None
        venue_match = re.search(r"at\s+([A-Za-z0-9\s\-,']+)", text, re.I)
        if not venue_match:
            venue_match = re.search(r"\(([A-Za-z0-9\s\-,']+)\)", text)
        if venue_match:
            venue = venue_match.group(1).strip()
        else:
            # try searching fixture element for a venue sub-element
            child_venue = fixture.find(class_=re.compile("venue", re.I))
            if child_venue:
                venue = child_venue.get_text(strip=True)

        if not venue:
            # auto-detect home if Munster listed first
            parts = teams.lower().split("vs")
            if parts and parts[0].strip() == TEAM_NAME.lower():
                venue = "Thomond Park"
            else:
                venue = "Venue TBC"

        # competition detection
        comp = "Other"
        comp_match = re.search(r"(United Rugby Championship|URC|European Rugby Champions Cup|Champions Cup|Friendly|Pre-Season)", text, re.I)
        if comp_match:
            raw = comp_match.group(1)
            if "United Rugby" in raw:
                comp = "URC"
            elif "Champions Cup" in raw or "European Rugby" in raw:
                comp = "ERCC"
            elif "Friendly" in raw or "Pre-Season" in raw:
                comp = "Friendly"
            else:
                comp = raw

        # broadcasters best-effort (look around fixture for Broadcast/TV text)
        broadcasters_text = "TBC"
        try:
            # Search inside fixture for 'Broadcast' or 'TV'
            bcast_el = fixture.find(text=re.compile(r"(Broadcast|TV|Live on|Broadcaster)", re.I))
            if bcast_el and bcast_el.parent:
                # collect nearby text
                nearby = bcast_el.parent.get_text(" ", strip=True)
                # extract broadcaster names (simple clean)
                possible = re.sub(r"Broadcast[:\s]*", "", nearby, flags=re.I).strip()
                if possible:
                    broadcasters_text = possible
        except Exception:
            broadcasters_text = "TBC"

        matches.append({
            "teams": teams.strip(),
            "datetime": dt,
            "venue": venue,
            "competition": comp,
            "broadcasters": broadcasters_text,
            "source_text": text,
            "url": TEAM_URL
        })

    print(f"Found {len(matches)} future matches.")
    return matches

# ------------ Helpers for lineups, officials, form, tables (best-effort) ------------
def fetch_starting_xv_from_espn(game_id: Optional[str]) -> Tuple[Optional[List[str]], Optional[List[str]]]:
    """Best-effort: fetch starting XV from ESPN lineups page. Returns (home_list, away_list) or (None,None)."""
    if not game_id:
        return None, None
    url = f"https://www.espn.com/rugby/lineups/_/gameId/{game_id}"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        # ESPN HTML changes; best-effort: look for starter names
        starters = soup.select(".lineup__player, .player-name, .lineup .starter")
        if not starters:
            # fallback: any strong tags in a lineup table
            starters = soup.select("table tr td")
        names = [s.get_text(strip=True) for s in starters if s.get_text(strip=True)]
        if len(names) < 2:
            return None, None
        half = len(names) // 2
        return names[:half], names[half:]
    except Exception as e:
        print(f"ESPN lineup fetch error: {e}")
        return None, None

def fetch_ultimate_rugby_lineups(match) -> Tuple[Optional[List[str]], Optional[List[str]]]:
    """Placeholder: attempt to fetch lineups from UltimateRugby; returns None,None currently."""
    # Ultimate Rugby parsing often requires heavier parsing and may block. Keep placeholder for now.
    return None, None

def fetch_starting_xv(game_id: Optional[str], match) -> Tuple[Optional[List[str]], Optional[List[str]]]:
    home, away = fetch_starting_xv_from_espn(game_id)
    if home and away:
        return home, away
    return fetch_ultimate_rugby_lineups(match)

def format_starting_xv_block(home_name: str, away_name: str, home_players: List[str], away_players: List[str]) -> str:
    """
    Returns a preformatted code block showing starting XV with middle column as #
    Uses monospaced alignment to look good on Reddit.
    """
    # column widths (tweakable)
    left_w = max(12, max((len(p) for p in home_players), default=12))
    right_w = max(12, max((len(p) for p in away_players), default=12))
    header = f"{home_name:<{left_w}} {'#':^5} {away_name:>{right_w}}"
    lines = [header]
    for i in range(15):
        h = home_players[i] if i < len(home_players) else ""
        a = away_players[i] if i < len(away_players) else ""
        lines.append(f"{h:<{left_w}} {str(i+1):^5} {a:>{right_w}}")
    return "```\n" + "\n".join(lines) + "\n```"

def fetch_officials_from_source(match) -> Optional[str]:
    """Best-effort: try to parse referee info from match['source_text'] or rugbykickoff page."""
    text = match.get("source_text", "")
    # look for 'Ref:' or 'Referee' or 'TMO'
    ref_match = re.search(r"(Referee|Ref)\s*[:\-]?\s*([A-Za-z \.]+)", text, re.I)
    if ref_match:
        return ref_match.group(0)
    # fallback: None
    return None

def fetch_recent_form(match) -> Tuple[Optional[str], Optional[str]]:
    """Placeholder: returns None; can be implemented by scraping results pages."""
    return None, None

def fetch_competition_table(marketing_comp: str) -> Optional[str]:
    """
    Best-effort fetch of competition table for the match competition.
    Returns a markdown table string or None if not available.
    (This is a simplified placeholder — real tables need structured source parsing.)
    """
    # For now return None to avoid posting inaccurate/unparseable tables.
    # Implementing a robust competition table scraper requires stable source & careful parsing.
    return None

# ------------ Reddit client ------------
def reddit_client():
    return praw.Reddit(
        client_id=os.getenv("REDDIT_CLIENT_ID"),
        client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
        username=os.getenv("REDDIT_USERNAME"),
        password=os.getenv("REDDIT_PASSWORD"),
        user_agent=os.getenv("USER_AGENT")
    )

# ------------ Posting logic ------------
def post_match_thread(match):
    """Create and submit match thread, then save submission id to posted.json."""
    try:
        reddit = reddit_client()
        subreddit = reddit.subreddit(SUBREDDIT)

        kickoff_local = match["datetime"].astimezone(IRELAND_TZ)
        teams = match["teams"].replace("vs", "vs.").strip()
        parts = teams.split(" vs.")
        home_name = parts[0].strip() if len(parts) >= 2 else TEAM_NAME
        away_name = parts[1].strip() if len(parts) >= 2 else "Opponent"

        # Try to fetch Starting XV (game_id unknown -> placeholder)
        game_id = None  # If you can map matches to ESPN gameId, set here
        home_players, away_players = fetch_starting_xv(game_id, match)
        if not (home_players and away_players):
            # placeholder names if no data available
            home_players = [f"Player {i}" for i in range(1, 16)]
            away_players = [f"Player {chr(64+i)}" for i in range(1, 16)]

        starting_xv_block = format_starting_xv_block(home_name, away_name, home_players, away_players)

        # Officials and recent form best-effort
        officials_text = fetch_officials_from_source(match) or ""
        home_form, away_form = fetch_recent_form(match)

        competition_table_md = fetch_competition_table(match.get("competition"))

        title = (
            f"Match Thread: {match['teams'].replace('vs', 'vs.')} – "
            f"{match['competition']} – "
            f"{kickoff_local.strftime('%a %d %b %Y @ %H:%Mhrs (IST)')} – "
            f"{match['venue']}"
        )

        # Build body
        body_lines = []
        body_lines.append(f"🏆 **Competition:** {match['competition']}")
        body_lines.append(f"🕖 **Kickoff:** {kickoff_local.strftime('%a %d %b %Y, %H:%M (IST)')} – {match['venue']}")
        if match.get("broadcasters"):
            body_lines.append(f"📺 **Broadcasters:** {match.get('broadcasters')}")
        if officials_text:
            body_lines.append(f"⚖️ **Officials:** {officials_text}")
        body_lines.append("")
        body_lines.append(f"👊 **Teams:** {match['teams'].replace('vs', 'vs.').strip()}")
        body_lines.append("")
        body_lines.append(f"🏉 **Starting XV:**")
        body_lines.append(starting_xv_block)
        body_lines.append("")

        if competition_table_md:
            body_lines.append("📊 **Competition Table**")
            body_lines.append(competition_table_md)
            body_lines.append("")

        if home_form or away_form:
            # If form available, format
            if home_form:
                body_lines.append(f"📈 **Recent Form — {home_name}:** {home_form}")
            if away_form:
                body_lines.append(f"📈 **Recent Form — {away_name}:** {away_form}")
            body_lines.append("")

        body_lines.append("💬 **Discuss below!**")
        body_lines.append("")
        body_lines.append("**Stand Up And Fight! 💪🔴**")
        body_lines.append("")
        body_lines.append("*Posted by MunsterKickoff 🤖 – created by /u/i93*")

        body = "\n".join(body_lines)

        # Submit post
        submission = subreddit.submit(title, selftext=body)
        # Select flair
        try:
            submission.flair.select(FLAIR_ID)
        except Exception as e:
            print(f"Warning: could not set flair: {e}")

        print(f"✅ Posted: {title} (id: {submission.id})")

        # Save posted entry with submission id and match datetime ISO format
        entry = {
            "teams": match["teams"],
            "datetime": match["datetime"].astimezone(ZoneInfo("UTC")).isoformat(),
            "competition": match["competition"],
            "venue": match["venue"],
            "submission_id": submission.id,
            "result_posted": False,
            "source_url": match.get("url")
        }
        add_posted_entry(entry)

    except Exception as e:
        print(f"❌ Error posting match thread: {e}")
        # don't crash workflow entirely with obscure exceptions; exit with code 1 so GH action shows fail
        sys.exit(1)

# ------------ MAIN ------------
if __name__ == "__main__":
    matches = get_munster_matches()
    if not matches:
        print("No matches found.")
        sys.exit(0)

    print("\nUpcoming Munster matches found:")
    for m in matches:
        kickoff_local = m["datetime"].astimezone(IRELAND_TZ)
        print(f"- {m['teams']} | {m['competition']} | Kickoff (IST): {kickoff_local.strftime('%a %d %b %Y %H:%M')} | Venue: {m['venue']}")

    # find today's match (within 24h UTC window)
    now_utc = datetime.now(ZoneInfo("UTC"))
    today_match = None
    for m in matches:
        if 0 <= (m["datetime"] - now_utc).total_seconds() < 86400:
            today_match = m
            break

    if today_match:
        post_time = get_post_time(today_match)
        now = datetime.now(ZoneInfo("UTC"))
        local_post_time = post_time.astimezone(IRELAND_TZ)
        print(f"\nToday's match scheduled for posting: {today_match['teams']} at {local_post_time.strftime('%a %d %b %Y %H:%M (IST)')}")
        if now >= post_time:
            # check if already posted
            posted = load_posted()
            already = any(entry.get("teams") == today_match["teams"] for entry in posted)
            if already:
                print("Already posted today. Exiting.")
            else:
                post_match_thread(today_match)
        else:
            print("Not yet time to post (waiting for 4 hours before kickoff).")
    else:
        print("No Munster match today or already posted.")
